import asyncio

from crm_mcp_client import CRMClient


def test_mcp_resolves_ticket_and_user_context() -> None:
    async def scenario() -> None:
        async with CRMClient() as crm:
            context = await crm.resolve_context(ticket_id="TCK-102")
            assert context.ticket is not None
            assert context.ticket["error_code"] == "protocol_mismatch"
            assert context.user is not None
            assert context.user["app_version"] == "0.0.9"

    asyncio.run(scenario())


def test_mcp_rejects_ticket_user_mismatch() -> None:
    async def scenario() -> None:
        async with CRMClient() as crm:
            try:
                await crm.resolve_context("TCK-101", "usr_1002")
            except ValueError as exc:
                assert "другому пользователю" in str(exc)
            else:
                raise AssertionError("Expected ticket/user mismatch")

    asyncio.run(scenario())
