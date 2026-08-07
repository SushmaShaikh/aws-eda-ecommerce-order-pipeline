import json
import os
import boto3

dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "Orders")
table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    """
    Triggered by SQS (processing-queue).
    SQS delivers a batch of records; each record's body contains the
    EventBridge event (which wraps our order detail).
    """
    for record in event["Records"]:
        try:
            eventbridge_event = json.loads(record["body"])
            order = eventbridge_event.get("detail", eventbridge_event)
            order_id = order["orderId"]

            # Simulate processing logic here (e.g. inventory check,
            # fraud check, etc.) before marking the order processed.
            table.update_item(
                Key={"orderId": order_id},
                UpdateExpression="SET #s = :status, processedAt = :ts",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":status": "PROCESSED",
                    ":ts": eventbridge_event.get("time", ""),
                },
            )
            print(f"Order {order_id} marked as PROCESSED")

        except Exception as e:
            # Raising re-queues the message; after maxReceiveCount
            # retries, SQS moves it to the configured DLQ automatically.
            print(f"Failed to process record: {record.get('body')} — {e}")
            raise

    return {"statusCode": 200}
