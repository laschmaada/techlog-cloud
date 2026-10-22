"""Cognito PostConfirmation trigger.

Every self-registered user is added to the Mechanic group, so a new
account can sign in and raise defects immediately after confirming its
email. Certifying staff are promoted by an administrator only — this
trigger never grants the Certifying group.
"""

from __future__ import annotations

DEFAULT_GROUP = "Mechanic"

_client = None


def _cognito():
    # Lazy import: boto3 exists in the Lambda runtime; keeping the import
    # here also lets the module import cleanly in local unit tests.
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("cognito-idp")
    return _client


def handler(event, context=None):
    if event.get("triggerSource") == "PostConfirmation_ConfirmSignUp":
        _cognito().admin_add_user_to_group(
            UserPoolId=event["userPoolId"],
            Username=event["userName"],
            GroupName=DEFAULT_GROUP,
        )
    return event
