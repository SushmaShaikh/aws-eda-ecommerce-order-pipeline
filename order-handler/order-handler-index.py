import json
import os
import uuid
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb")
eventbridge = boto3.client("events")

TABLE_NAME = os.environ.get("TABLE_NAME", "Orders")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "default")

table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    """
    Triggered by API Gateway (HTTP API) on POST /orders, behind a Cognito
    JWT authorizer.
    1. Reads the caller's identity from the *verified* Cognito token
       (never trusts a customerId supplied in the request body)
    2. Parses the order items from the request body
    3. Writes it to DynamoDB with status PENDING
    4. Publishes an OrderPlaced event to EventBridge
    """
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    # The API Gateway JWT authorizer has already validated the token by the
    # time this Lambda runs. We read the customer's identity from the
    # verified claims, NOT from the request body — this means a customer
    # can never place an order pretending to be someone else, even if they
    # tamper with the JSON payload.
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
        customer_id = claims["sub"]
    except KeyError:
        return _response(401, {"error": "Missing or invalid authorization"})

    items = body.get("items")

    if not items:
        return _response(400, {"error": "items are required"})

    order_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    order_record = {
        "orderId": order_id,
        "customerId": customer_id,
        "items": items,
        "status": "PENDING",
        "createdAt": timestamp,
    }

    # 1. Write order to DynamoDB
    table.put_item(Item=order_record)

    # 2. Publish OrderPlaced event to EventBridge
    eventbridge.put_events(
        Entries=[
            {
                "Source": "ecommerce.orders",
                "DetailType": "OrderPlaced",
                "Detail": json.dumps(order_record),
                "EventBusName": EVENT_BUS_NAME,
            }
        ]
    )

    return _response(202, {"orderId": order_id, "status": "PENDING"})


def _response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body_dict),
    }
