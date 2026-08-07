# Event-Driven E-Commerce Order Pipeline on AWS

![AWS](https://img.shields.io/badge/AWS-232F3E?style=flat&logo=amazonaws&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![EventBridge](https://img.shields.io/badge/EventBridge-FF4F8B?style=flat)
![Serverless](https://img.shields.io/badge/Serverless-FD5750?style=flat)
![Status](https://img.shields.io/badge/status-tested%20end--to--end-brightgreen?style=flat)

A fully serverless, event-driven order processing pipeline built to deepen my
hands-on understanding of event-driven architecture on AWS — ahead of AWS
Solutions Architect interviews. Every service below was deployed and tested
against a live account, not just diagrammed.

## Architecture

```mermaid
flowchart TD
    Customer([Customer places order])
    APIGW[API Gateway]
    Lambda1[Lambda: Order Handler]
    DDB[(DynamoDB: Orders)]
    EB{{EventBridge: OrderPlaced}}

    Customer --> APIGW --> Lambda1
    Lambda1 --> DDB
    Lambda1 --> EB

    EB --> SQS1[[SQS: Processing Queue]]
    EB --> SQS2[[SQS: Notification Queue]]

    SQS1 --> Lambda2[Lambda: Process Order]
    Lambda2 --> DDB

    SQS2 --> Lambda3[Lambda: Send Notification]
    Lambda3 --> SNS([SNS: Order Confirmation])

    classDef sync fill:#4db8ff,stroke:#1a1a2e,color:#000
    classDef event fill:#ff9900,stroke:#1a1a2e,color:#000
    classDef queue fill:#4dff91,stroke:#1a1a2e,color:#000

    class Customer,APIGW,Lambda1,DDB sync
    class EB event
    class SQS1,SQS2,Lambda2,Lambda3,SNS queue
```
## Proof it works

**Order status flips from PENDING to PROCESSED in DynamoDB:**
![DynamoDB order processed](screenshots/dynamodb-processed.png)

**Confirmation email delivered via SNS:**
![Confirmation email](screenshots/confirmation-email.png)

**Lambda executing cleanly, visible in CloudWatch Logs:**
![CloudWatch logs](screenshots/cloudwatch-logs.png)

**EventBridge rule fanning out to both SQS queues:**
![EventBridge targets](screenshots/eventbridge-targets.png)

**Sample request and response via Postman:**
![Postman request](screenshots/postman-request.png)
**The core idea:** the customer only waits on the fast, synchronous part
(writing the order and getting an acknowledgment back). Everything else —
processing and notifying — happens asynchronously via EventBridge fanning
out to independent SQS-backed consumers, so a slow or failing downstream
service never blocks checkout.

## How it works

1. Customer submits an order via **API Gateway** (`POST /orders`)
2. The **Order Handler Lambda** writes the order to **DynamoDB** with status
   `PENDING`, then publishes an `OrderPlaced` event to **EventBridge**, and
   immediately returns a response — the customer never waits on anything
   downstream
3. **EventBridge** fans that single event out to two independent **SQS**
   queues, each with its own dead-letter queue for messages that fail
   repeatedly
4. **Process Order Lambda** consumes from the processing queue and updates
   the order's status in DynamoDB to `PROCESSED`
5. **Send Notification Lambda** consumes from the notification queue and
   publishes a confirmation message to **SNS**, which emails the customer

## Tech stack

| Service | Role |
|---|---|
| API Gateway | Public HTTP endpoint |
| Lambda (x3) | Order handling, processing, notification |
| DynamoDB | Order storage |
| EventBridge | Event bus / fan-out |
| SQS (+ DLQs) | Decoupling, buffering, retry/failure isolation |
| SNS | Customer notification delivery |

## Debugging notes from building this

Two real issues came up while building this — leaving them here since the
troubleshooting was as instructive as the build itself:

- **The EventBridge console wizard doesn't save a rule until you click the
  final "Create rule" button.** I navigated away mid-flow to go create the
  SQS queues first (since the console wanted a target before it would let me
  finish), and the entire in-progress rule was silently discarded — no
  warning, no draft saved. Diagnosed by tracing the failure backward: no
  Lambda logs → no messages ever reaching the queue → the rule wasn't even
  listed under Rules. Fixed by recreating the rule in a single pass, adding
  both SQS targets before clicking "Create rule."

- **SNS FIFO topics only support SQS as a subscriber protocol — not email.**
  I'd created the notification topic as FIFO by default, then couldn't
  figure out why "Email" wasn't showing up as an option in the subscription
  protocol dropdown. Recreated the topic as Standard type and email
  subscriptions worked immediately.

## Repo structure

```
order-handler/          Lambda 1 — receives order, writes to DynamoDB, publishes event
process-order/          Lambda 2 — updates order status (triggered by SQS)
send-notification/      Lambda 3 — sends SNS confirmation (triggered by SQS)
diagrams/               Architecture diagram source
eventbridge-rule-pattern.json   Event pattern used for the EventBridge rule
```

Each Lambda folder includes its code and the least-privilege IAM policy it
was deployed with (`REGION`/`ACCOUNT_ID` are placeholders — swap in your own
before deploying).

## Possible extensions

- Add a **Step Functions** orchestrator if a real payment/inventory check
  were introduced — needed to coordinate a "wait for both, then confirm or
  compensate" flow, which this simplified version doesn't require since its
  two consumers are fully independent
- **X-Ray** tracing across all three Lambdas for full request-path visibility
- **CloudWatch alarms** on each DLQ's message count to catch repeated
  failures proactively

## Testing

Tested end to end via a manual `POST /orders` request: confirmed the order
lands in DynamoDB as `PENDING`, flips to `PROCESSED` within seconds, and a
confirmation email is delivered via SNS.

```bash
curl -X POST https://YOUR-API-ID.execute-api.REGION.amazonaws.com/orders \
  -H "Content-Type: application/json" \
  -d '{"customerId": "cust-123", "items": [{"sku": "ABC-001", "qty": 2}]}'
```
