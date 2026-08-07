# E-Commerce EDA on AWS — Full Build Guide

Architecture: **API Gateway → Lambda → DynamoDB → EventBridge → SQS (x2) → Lambda → SNS**

Files in this package:
```
order-handler/index.py          Lambda 1 — receives order, writes to DynamoDB, publishes event
order-handler/iam-policy.json   IAM policy for Lambda 1
process-order/index.py          Lambda 2 — updates order status (triggered by SQS)
process-order/iam-policy.json   IAM policy for Lambda 2
send-notification/index.py      Lambda 3 — sends SNS confirmation (triggered by SQS)
send-notification/iam-policy.json  IAM policy for Lambda 3
eventbridge-rule-pattern.json   Event pattern for the EventBridge rule
```

Replace `REGION` and `ACCOUNT_ID` in every IAM policy file with your actual
values before attaching them.

---

## Step 1 — Create the DynamoDB table

1. Console → DynamoDB → **Create table**
2. Table name: `Orders`
3. Partition key: `orderId` (String)
4. Table settings: **Default settings** (on-demand capacity)
5. Create table

---

## Step 2 — Create the Order Handler Lambda

1. Console → Lambda → **Create function** → Author from scratch
2. Name: `order-handler`, Runtime: **Python 3.12**
3. Paste the contents of `order-handler/index.py` into the code editor
4. Configuration → Environment variables → add:
   - `TABLE_NAME` = `Orders`
   - `EVENT_BUS_NAME` = `default`
5. Configuration → Permissions → click the execution role → **Add permissions
   → Create inline policy** → paste `order-handler/iam-policy.json`
   (after replacing REGION/ACCOUNT_ID)
6. Deploy

---

## Step 3 — Create the API Gateway

1. Console → API Gateway → **Create API** → **HTTP API** → Build
2. Add integration: Lambda → select `order-handler`
3. Add route: `POST /orders`
4. Create a stage (e.g. `$default`) and deploy
5. Copy the **Invoke URL** — you'll use it to test in Step 8

---

## Step 4 — Create the EventBridge rule

1. Console → EventBridge → **Rules** → **Create rule**
2. Name: `order-placed-rule`, Event bus: `default`
3. Rule type: **Rule with an event pattern**
4. Event pattern: paste the contents of `eventbridge-rule-pattern.json`
5. You'll add targets in the next step, after the queues exist — save the
   rule with no targets for now, or come back to add them

---

## Step 5 — Create the two SQS queues (+ DLQs)

1. Console → SQS → **Create queue**
   - Name: `processing-queue-dlq` → Create (repeat for `notification-queue-dlq`)
2. Console → SQS → **Create queue**
   - Name: `processing-queue` → Standard type
   - Scroll to **Dead-letter queue** → Enable → select `processing-queue-dlq`
     → Maximum receives: `3`
   - Create queue. Repeat for `notification-queue` with `notification-queue-dlq`
3. Go back to your `order-placed-rule` from Step 4 → **Add target** twice:
   - Target 1: SQS queue → `processing-queue`
   - Target 2: SQS queue → `notification-queue`

---

## Step 6 — Create the Process Order Lambda

1. Console → Lambda → **Create function** → `process-order`, Python 3.12
2. Paste `process-order/index.py`
3. Environment variables: `TABLE_NAME` = `Orders`
4. Configuration → Triggers → **Add trigger** → SQS → select `processing-queue`
   (batch size 1–10 is fine to start)
5. Attach the inline policy from `process-order/iam-policy.json`
6. Deploy

---

## Step 7 — Create the SNS topic + Notification Lambda

1. Console → SNS → **Create topic** → Standard → name `order-confirmations`
2. **Create subscription** → Protocol: Email → enter your email → confirm via
   the link AWS emails you
3. Console → Lambda → **Create function** → `send-notification`, Python 3.12
4. Paste `send-notification/index.py`
5. Environment variables: `TOPIC_ARN` = *(copy the ARN from the SNS topic page)*
6. Configuration → Triggers → **Add trigger** → SQS → select `notification-queue`
7. Attach the inline policy from `send-notification/iam-policy.json`
8. Deploy

---

## Step 8 — Test end to end

From your terminal (replace the URL with your API Gateway Invoke URL):

```bash
curl -X POST https://YOUR-API-ID.execute-api.REGION.amazonaws.com/orders \
  -H "Content-Type: application/json" \
  -d '{
        "customerId": "cust-123",
        "items": [{"sku": "ABC-001", "qty": 2}]
      }'
```

Expected result:
1. Response comes back immediately: `{"orderId": "...", "status": "PENDING"}`
2. Check DynamoDB → `Orders` table → the item appears with status `PENDING`,
   then shortly after updates to `PROCESSED`
3. Check your email — you should receive the order confirmation from SNS

**If something doesn't show up:** check CloudWatch Logs for each Lambda
(Lambda → your function → Monitor → View CloudWatch logs). The most common
first-time issues are a missing IAM permission or the EventBridge pattern not
matching the `source`/`detail-type` your Lambda published — both show up
clearly in the logs.

---

## Optional next steps once this works

- Add a **Step Functions** orchestrator if you extend this to also involve
  a payment/inventory service that needs to coordinate before confirming
- Add **X-Ray** tracing (enable "Active tracing" on each Lambda and on API
  Gateway) to see the full request path across all three functions
- Add a **CloudWatch alarm** on each DLQ's `ApproximateNumberOfMessages` so
  you get notified if messages start failing repeatedly
