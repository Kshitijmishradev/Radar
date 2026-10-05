import unittest
from pathlib import Path


class DashboardAssetTests(unittest.TestCase):
    def test_dashboard_has_the_workflow_controls(self) -> None:
        root = Path(__file__).parents[1] / "app" / "dashboard"
        document = (root / "index.html").read_text()
        script = (root / "app.js").read_text()
        ai_document = (root / "ai.html").read_text()
        ai_script = (root / "ai.js").read_text()
        self.assertIn('id="actions-table"', document)
        self.assertIn('Switch role', document)
        self.assertIn('id="access-summary"', document)
        self.assertIn('id="coverage-ring"', document)
        self.assertIn('id="daily-spend-total"', document)
        self.assertIn('PENDING_APPROVAL', script)
        self.assertIn('DEMO_PERSONAS', script)
        self.assertIn('Approval requires the Approver role', script)
        self.assertIn('renderScanPattern', script)
        self.assertIn('/v1/actions/${actionId}/${command}', script)
        self.assertIn('Budget gate simulator', ai_document)
        self.assertIn('id="ai-access-note"', ai_document)
        self.assertIn('data-preflight-scenario="allow"', ai_document)
        self.assertIn('/v1/ai/preflight', ai_script)
        self.assertIn('Use ${escapeHtml(fallback.provider)}', ai_script)
        self.assertIn('Run Ollama request', ai_document)
        self.assertIn('/v1/ai/ollama/generate', ai_script)
        self.assertIn('Run 3-step RTX 4090 replay', ai_document)
        self.assertIn('/v1/ai/ollama/scenarios/rental-replay', ai_script)
        self.assertIn('Number(value) < 0.01', ai_script)
        self.assertIn('renderAIAccess', ai_script)
        self.assertIn('PREFLIGHT_SCENARIOS', ai_script)
