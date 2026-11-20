"""Submit pipeline outputs to the control plane for a person to approve."""

import json
import urllib.request


class ControlPlane:
    def __init__(self, base_url: str, actor: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.actor = actor
        self.timeout = timeout

    def propose(
        self,
        *,
        kind: str,
        name: str,
        content: dict,
        summary: str,
        parent_artifact_id: str | None = None,
    ) -> dict:
        """Store the content and open a proposal, unless it equals the latest version."""
        artifact = self._post(
            "/artifacts",
            {"kind": kind, "name": name, "created_by": self.actor, "content_json": content},
        )
        if artifact.get("existing"):
            return {"artifact": artifact, "proposal": None}
        body = {
            "artifact_id": artifact["id"],
            "summary": summary,
            "submitted_by": self.actor,
        }
        if parent_artifact_id:
            body["parent_artifact_id"] = parent_artifact_id
        proposal = self._post("/proposals", body)
        return {"artifact": artifact, "proposal": proposal}

    def _post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())
