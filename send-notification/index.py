import json
import os
import boto3

sns = boto3.client("sns")

TOPIC_ARN = os.environ["TOPIC_ARN"]  # set as a Lambda environment variable


def lambda_handler(event, context):
    """
    Triggered by SQS (notification-queue).
    Publishes an order confirmation message to the SNS topic,
    which fans out to email/SMS subscribers.
    """
    for record in event["Records"]:
        try:
            eventbridge_event = json.loads(record["body"])
            order = eventbridge_event.get("detail", eventbridge_event)
            order_id = order["orderId"]
            customer_id = order["customerId"]

            message = (
                f"Hi! Your order {order_id} has been received "
                f"and is being processed. Thank you for your purchase!"
            )

            sns.publish(
                TopicArn=TOPIC_ARN,
                Subject=f"Order Confirmation - {order_id}",
                Message=message,
                MessageAttributes={
                    "customerId": {"DataType": "String", "StringValue": customer_id}
                },
            )
            print(f"Notification sent for order {order_id}")

        except Exception as e:
            print(f"Failed to send notification: {record.get('body')} — {e}")
            raise

    return {"statusCode": 200}
