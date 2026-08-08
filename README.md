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
![image](./diagrams/aws-eda-ecommerce-order-pipeline%20architecture.png)

**The core idea:** the customer only waits on the fast, synchronous part
(writing the order and getting an acknowledgment back). Everything else —
processing and notifying — happens asynchronously via EventBridge fanning
out to independent SQS-backed consumers, so a slow or failing downstream
service never blocks checkout.

## How it works

1. Customer submits an order via **API Gateway** (`POST /orders`), with a
   Cognito-issued access token in the `Authorization` header
2. API Gateway's **Cognito JWT authorizer** validates the token before the
   request ever reaches application code — an invalid or missing token is
   rejected with a `401`
3. The **Order Handler Lambda** reads the caller's identity from the
   *verified* token claims (never from the request body, so a customer can
   never place an order pretending to be someone else), writes the order to
   **DynamoDB** with status `PENDING`, then publishes an `OrderPlaced` event
   to **EventBridge**, and immediately returns a response — the customer
   never waits on anything downstream
4. **EventBridge** fans that single event out to two independent **SQS**
   queues, each with its own dead-letter queue for messages that fail
   repeatedly
5. **Process Order Lambda** consumes from the processing queue and updates
   the order's status in DynamoDB to `PROCESSED`
6. **Send Notification Lambda** consumes from the notification queue and
   publishes a confirmation message to **SNS**, which emails the customer

## Tech stack

| Service | Role |
|---|---|
| Cognito | Authentication — issues and validates JWTs |
| API Gateway | Public HTTP endpoint, enforces the Cognito authorizer |
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

- **Cognito's "Create user" screen doesn't actually offer a true permanent
  password, despite the label.** Both options under its password section
  ("Set a password" / "Generate a password") still create the user with a
  `FORCE_CHANGE_PASSWORD` status, which then causes a misleading
  `NotAuthorizedException: Incorrect username or password` error from
  `initiate-auth` — the real problem has nothing to do with the password
  itself. Fixed by explicitly forcing a permanent password via the CLI:
  `aws cognito-idp admin-set-user-password --user-pool-id POOL_ID
  --username EMAIL --password 'Pass123!' --permanent`. The `--permanent`
  flag is the piece the console UI has no equivalent for.

## Security

The `POST /orders` route is protected by a **Cognito JWT authorizer** on API
Gateway — every request must carry a valid, signed access token issued by a
Cognito User Pool. Two things worth calling out beyond "there's a login now":

- **Authorization happens before the request reaches application code.**
  API Gateway rejects an invalid or missing token with a `401` on its own —
  the Lambda never even runs for an unauthenticated request.
- **The Lambda trusts the verified token claims, not the request body.**
  The customer's identity comes from the token's `sub` claim
  (`event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]`), not
  from a `customerId` field a client could simply type into the JSON
  payload. This closes a real vulnerability: without this, any
  authenticated user could place an order under someone else's customer ID
  just by editing the request body.

**Setup summary** (Cognito → API Gateway wiring):

1. Cognito User Pool + a **public app client** (SPA type, no client secret
   — there's no backend here to safely hold one)
2. `ALLOW_USER_PASSWORD_AUTH` enabled on the app client, so a token can be
   fetched directly via `aws cognito-idp initiate-auth` for testing, rather
   than requiring a hosted login page
3. An API Gateway **JWT authorizer**, configured with:
   - Issuer URL: `https://cognito-idp.<region>.amazonaws.com/<user-pool-id>`
   - Audience: the app client ID
4. The authorizer attached directly to the `POST /orders` route

Verified both directions in Postman: a request with a valid Bearer token
returns `202`; the same request with the `Authorization` header removed
returns `401`.

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
  -H "Authorization: Bearer YOUR_COGNITO_ACCESS_TOKEN" \
  -d '{"items": [{"sku": "ABC-001", "qty": 2}]}'
```

Verified both directions: a request with a valid token returns `202`, and
the same request with the `Authorization` header removed entirely returns
`401` — confirming the authorizer is actually enforcing, not just present.

## Proof it works

**Order status flips from PENDING to PROCESSED in DynamoDB:**
![DynamoDB order processed](screenshots/dynamodb-processed.png)

**Confirmation email delivered via SNS:**
![Confirmation email](screenshots/confirmation-email.png)

**Lambda executing cleanly, visible in CloudWatch Logs:**
![CloudWatch logs](screenshots/cloudwatch-logs.png)

**One EventBridge rule fanning a single `OrderPlaced` event out to two
independent SQS queues:**
![EventBridge targets](screenshots/eventbridge-targets.png)

**Authenticated request accepted (202) vs. unauthenticated request rejected
(401) — confirming the Cognito authorizer is actually enforcing, not just
present:**
![Postman authenticated ](screenshots/postman-auth-vs-202.png)

![Postman rejected](screenshots/postman-auth-401.png)