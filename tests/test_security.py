import unittest

from app.security import Principal, Role, SessionSigner


class SessionSignerTests(unittest.TestCase):
    def test_signed_session_round_trip(self) -> None:
        signer = SessionSigner("test-secret")
        original = Principal("alex", "acme", Role.APPROVER)
        verified = signer.verify(signer.issue(original))
        self.assertEqual(verified, original)

    def test_tampered_session_is_rejected(self) -> None:
        signer = SessionSigner("test-secret")
        token = signer.issue(Principal("alex", "acme", Role.VIEWER))
        with self.assertRaises(ValueError):
            signer.verify(token[:-1] + "x")

    def test_admin_can_perform_any_role_action(self) -> None:
        self.assertTrue(Principal("alex", "acme", Role.ADMIN).allows(Role.OPERATOR))

    def test_role_permissions_do_not_expand_beyond_the_assigned_role(self) -> None:
        self.assertTrue(Principal("priya", "acme", Role.APPROVER).allows(Role.APPROVER))
        self.assertFalse(Principal("priya", "acme", Role.APPROVER).allows(Role.OPERATOR))
        self.assertFalse(Principal("jordan", "acme", Role.VIEWER).allows(Role.APPROVER))
