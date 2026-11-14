"""
DynamoDB Memory — stores conversation history in AWS DynamoDB.
Refactored from Milestone 2 to conform to the ConversationMemory protocol.
"""

import time
from typing import Dict, List

import boto3
from botocore.exceptions import ClientError

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DynamoDBMemory:
    """DynamoDB-backed conversation memory implementation."""

    def __init__(self) -> None:
        self.dynamodb = boto3.resource(
            "dynamodb", region_name=settings.AWS_REGION
        )
        self.table_name = settings.DYNAMODB_TABLE_NAME
        self.table = self._get_or_create_table()

    def _get_or_create_table(self):
        """Gets the DynamoDB table, creating it if it doesn't exist."""
        try:
            table = self.dynamodb.Table(self.table_name)
            table.load()
            return table
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.info(f"Creating DynamoDB table {self.table_name}")
                table = self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {"AttributeName": "session_id", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "session_id", "AttributeType": "S"},
                        {"AttributeName": "timestamp", "AttributeType": "N"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                table.meta.client.get_waiter("table_exists").wait(
                    TableName=self.table_name
                )
                logger.info("Table created successfully")
                return table
            else:
                logger.error(f"Error accessing DynamoDB table: {e}")
                raise

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Adds a message to the chat history."""
        try:
            self.table.put_item(
                Item={
                    "session_id": session_id,
                    "timestamp": int(time.time() * 1000),
                    "role": role,
                    "content": content,
                }
            )
        except Exception as e:
            logger.error(f"Error adding message to DynamoDB: {e}")
            raise

    def get_history(
        self, session_id: str, limit: int = 10
    ) -> List[Dict[str, str]]:
        """Retrieves chat history for a session in chronological order."""
        try:
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key(
                    "session_id"
                ).eq(session_id),
                ScanIndexForward=False,  # Latest first
                Limit=limit,
            )
            # Reverse to return chronological order
            items = response.get("Items", [])
            items.reverse()
            return [
                {"role": item["role"], "content": item["content"]}
                for item in items
            ]
        except Exception as e:
            logger.error(f"Error retrieving history from DynamoDB: {e}")
            return []
