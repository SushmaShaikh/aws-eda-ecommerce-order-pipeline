## Architecture

```mermaid
flowchart TD
    Customer([Customer places order])
    Cognito[Cognito: JWT Authorizer]
    APIGW[API Gateway]
    Lambda1[Lambda: Order Handler]
    DDB[(DynamoDB: Orders)]
    EB{{EventBridge: OrderPlaced}}

    Customer -->|Bearer token| APIGW
    APIGW -->|validates token| Cognito
    Cognito -->|verified claims| Lambda1
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
    classDef security fill:#e74c3c,stroke:#1a1a2e,color:#fff

    class Customer,APIGW,Lambda1,DDB sync
    class EB event
    class SQS1,SQS2,Lambda2,Lambda3,SNS queue
    class Cognito security
```

**The core idea:** the customer only waits on the fast, synchronous part
(writing the order and getting an acknowledgment back). Everything else —
processing and notifying — happens asynchronously via EventBridge fanning
out to independent SQS-backed consumers, so a slow or failing downstream
service never blocks checkout.