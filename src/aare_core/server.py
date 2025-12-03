"""
aare-core HTTP Server - Flask-based verification API

Start with:
    aare-serve
    # or
    python -m aare_core.server

Optional persistence:
    Set AARE_PERSISTENCE=sqlite:///path/to/db.sqlite to enable audit trail.
    Or AARE_PERSISTENCE=memory for in-memory (testing only).
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional

try:
    from flask import Flask, request, jsonify
except ImportError:
    raise ImportError(
        "Flask is required for the server. Install with: pip install aare-core[server]"
    )

from .ontology_loader import OntologyLoader
from .llm_parser import LLMParser
from .smt_verifier import SMTVerifier
from .persistence import (
    VerificationStore,
    VerificationRecord,
    SQLiteStore,
    InMemoryStore,
    StorageError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _init_persistence() -> Optional[VerificationStore]:
    """Initialize persistence store from environment configuration."""
    persistence_uri = os.environ.get("AARE_PERSISTENCE", "").strip()

    if not persistence_uri:
        return None

    if persistence_uri == "memory":
        logger.info("Persistence enabled: in-memory store")
        return InMemoryStore()

    if persistence_uri.startswith("sqlite://"):
        db_path = persistence_uri[9:]  # Remove "sqlite://" prefix
        if not db_path:
            db_path = "verifications.db"
        logger.info(f"Persistence enabled: SQLite at {db_path}")
        return SQLiteStore(db_path)

    logger.warning(f"Unknown persistence URI: {persistence_uri}, persistence disabled")
    return None


def create_app(ontology_dir=None, store: Optional[VerificationStore] = None):
    """
    Create Flask application.

    Args:
        ontology_dir: Directory containing ontology JSON files
        store: Optional VerificationStore for persisting verification records.
               If not provided, checks AARE_PERSISTENCE environment variable.
    """
    app = Flask(__name__)

    # Initialize components
    ontology_loader = OntologyLoader(ontology_dir)
    llm_parser = LLMParser()
    smt_verifier = SMTVerifier()

    # Initialize persistence (optional)
    verification_store = store or _init_persistence()

    # CORS configuration from environment
    allowed_origins = os.environ.get(
        "CORS_ORIGINS",
        "https://aare.ai,https://www.aare.ai,http://localhost:8000,http://localhost:3000,*"
    ).split(",")

    def get_cors_origin(request_origin):
        """Get allowed CORS origin"""
        if "*" in allowed_origins:
            return "*"
        if request_origin in allowed_origins:
            return request_origin
        return allowed_origins[0] if allowed_origins else ""

    @app.after_request
    def add_cors_headers(response):
        """Add CORS headers to all responses"""
        origin = request.headers.get("Origin", "")
        response.headers["Access-Control-Allow-Origin"] = get_cors_origin(origin)
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,x-api-key,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "OPTIONS,POST,GET"
        return response

    @app.route("/verify", methods=["POST", "OPTIONS"])
    def verify():
        """Verify LLM output against compliance constraints"""
        if request.method == "OPTIONS":
            return "", 204

        verification_id = str(uuid.uuid4())

        try:
            request_json = request.get_json(silent=True)

            if not request_json:
                return jsonify({"error": "Invalid JSON in request body"}), 400

            llm_output = request_json.get("llm_output", "")
            ontology_name = request_json.get("ontology", "example")

            if not llm_output:
                return jsonify({"error": "llm_output is required"}), 400

            logger.info(f"[{verification_id}] Verifying with ontology={ontology_name}")

            # Load ontology
            ontology = ontology_loader.load(ontology_name)

            # Parse LLM output
            extracted_data = llm_parser.parse(llm_output, ontology)

            # Verify constraints
            result = smt_verifier.verify(extracted_data, ontology)

            timestamp = datetime.utcnow().isoformat()

            response_body = {
                "verified": result["verified"],
                "violations": result["violations"],
                "parsed_data": extracted_data,
                "ontology": {
                    "name": ontology["name"],
                    "version": ontology["version"],
                    "constraints_checked": len(ontology["constraints"])
                },
                "proof": result["proof"],
                "verification_id": verification_id,
                "execution_time_ms": result["execution_time_ms"],
                "timestamp": timestamp
            }

            # Persist verification record if store is configured
            if verification_store:
                try:
                    record = VerificationRecord.from_verification_result(
                        verification_id=verification_id,
                        ontology_name=ontology["name"],
                        result=result,
                        parsed_data=extracted_data,
                        llm_output=llm_output,
                        timestamp=timestamp
                    )
                    certificate_hash = verification_store.store(record)
                    response_body["certificate_hash"] = certificate_hash
                except StorageError as e:
                    # Log but don't fail the verification
                    logger.warning(f"[{verification_id}] Persistence failed: {e}")

            logger.info(f"[{verification_id}] Result: verified={result['verified']}")
            return jsonify(response_body), 200

        except Exception as e:
            logger.error(f"[{verification_id}] Error: {e}", exc_info=True)
            return jsonify({
                "error": str(e),
                "type": type(e).__name__,
                "verification_id": verification_id
            }), 500

    @app.route("/ontologies", methods=["GET"])
    def list_ontologies():
        """List available ontologies"""
        try:
            ontologies = ontology_loader.list_available()
            return jsonify({"ontologies": ontologies}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/ontologies/<name>", methods=["GET"])
    def get_ontology(name):
        """Get a specific ontology definition"""
        try:
            ontology = ontology_loader.load(name)
            return jsonify(ontology), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 404

    @app.route("/verifications/<verification_id>", methods=["GET"])
    def get_verification(verification_id):
        """Retrieve a stored verification record by ID (requires persistence)"""
        if not verification_store:
            return jsonify({
                "error": "Persistence not enabled",
                "hint": "Set AARE_PERSISTENCE environment variable"
            }), 501

        try:
            record = verification_store.retrieve(verification_id)
            if not record:
                return jsonify({"error": "Verification not found"}), 404

            return jsonify({
                "verification_id": record.verification_id,
                "ontology_name": record.ontology_name,
                "timestamp": record.timestamp,
                "verified": record.verified,
                "violations": record.violations,
                "violation_count": record.violation_count,
                "execution_time_ms": record.execution_time_ms,
                "certificate_hash": record.certificate_hash,
                "input_hash": record.input_hash
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/verifications", methods=["GET"])
    def list_verifications():
        """List recent verification records (requires persistence)"""
        if not verification_store:
            return jsonify({
                "error": "Persistence not enabled",
                "hint": "Set AARE_PERSISTENCE environment variable"
            }), 501

        try:
            limit = request.args.get("limit", 100, type=int)
            limit = min(limit, 1000)  # Cap at 1000
            records = verification_store.list_recent(limit)

            return jsonify({
                "verifications": [
                    {
                        "verification_id": r.verification_id,
                        "ontology_name": r.ontology_name,
                        "timestamp": r.timestamp,
                        "verified": r.verified,
                        "violation_count": r.violation_count,
                        "certificate_hash": r.certificate_hash
                    }
                    for r in records
                ],
                "count": len(records)
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint"""
        return jsonify({
            "status": "healthy",
            "service": "aare-core",
            "persistence": verification_store is not None
        }), 200

    @app.route("/", methods=["GET"])
    def root():
        """Root endpoint with API documentation"""
        endpoints = {
            "POST /verify": "Verify LLM output against compliance constraints",
            "GET /ontologies": "List available ontologies",
            "GET /ontologies/<name>": "Get ontology definition",
            "GET /health": "Health check"
        }

        if verification_store:
            endpoints["GET /verifications"] = "List recent verification records"
            endpoints["GET /verifications/<id>"] = "Retrieve verification by ID"

        return jsonify({
            "service": "aare-core",
            "description": "Z3 SMT verification engine for LLM compliance",
            "persistence": verification_store is not None,
            "endpoints": endpoints,
            "documentation": "https://github.com/aare-ai/aare-core"
        }), 200

    return app


# Allow running as module
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=True)
