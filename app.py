"""Flask application for Study Buddy RAG system.

Main web server wiring together all modules: configuration, database,
file processing, RAG engine, LLM providers, and PDF generation.
Serves the single-page frontend and handles REST API + Socket.IO events.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from flask_socketio import SocketIO, emit

from config import ConfigManager
from database import Database
from file_processor import FileProcessor
from llm_providers import LLMError, get_provider
from pdf_generator import PDFGenerator, get_question_paper_prompt, get_study_material_prompt
from rag_engine import RAGEngine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App initialisation
# Check if running in a PyInstaller bundle
if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(bundle_dir, "templates")
    static_dir = os.path.join(bundle_dir, "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
else:
    app = Flask(__name__)

app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB max upload

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# Singletons
config_manager = ConfigManager()
db = Database()
file_processor = FileProcessor()
pdf_generator = PDFGenerator()

# Upload directory for conversation files
UPLOAD_BASE_DIR = Path.home() / ".studybuddy" / "uploads"
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Cache RAG engines per conversation (thread-safe)
_rag_cache: dict[str, RAGEngine] = {}
_rag_lock = threading.Lock()


def _get_rag_engine(conversation_id: str) -> RAGEngine:
    """Get or create a RAG engine for a conversation."""
    with _rag_lock:
        if conversation_id not in _rag_cache:
            _rag_cache[conversation_id] = RAGEngine(conversation_id=conversation_id)
        return _rag_cache[conversation_id]


def _get_llm_provider():
    """Build an LLM provider from current config."""
    settings = config_manager.get_all_settings()
    provider_name = settings.get("active_provider", "openai")

    provider_config: dict[str, Any] = {}

    if provider_name in ("openai", "gemini", "claude"):
        api_key = config_manager.get_api_key(provider_name)
        if api_key:
            provider_config["api_key"] = api_key

    if provider_name == "ollama":
        ollama_settings = config_manager.get_ollama_settings()
        provider_config["base_url"] = ollama_settings.get("base_url", "http://localhost:11434")
        provider_config["model"] = ollama_settings.get("model", "llama3")

    if provider_name == "llamacpp":
        llama_settings = config_manager.get_llamacpp_settings()
        provider_config["model_path"] = llama_settings.get("model_path", "")

    return get_provider(provider_name, provider_config)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the main single-page application."""
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/config/status", methods=["GET"])
def config_status():
    """Check if at least one provider is configured."""
    configured = config_manager.is_configured()
    active = config_manager.get_active_provider() or "none"
    return jsonify({
        "configured": configured,
        "active_provider": active,
    })


@app.route("/api/config/settings", methods=["GET"])
def config_settings():
    """Return all current settings (API keys masked)."""
    settings = config_manager.get_all_settings()
    # Mask API keys for security
    masked = dict(settings)
    if "api_keys" in masked:
        for provider, key in masked["api_keys"].items():
            if key and len(key) > 8:
                masked["api_keys"][provider] = key[:4] + "****" + key[-4:]
            elif key:
                masked["api_keys"][provider] = "****"

    # Add convenience top-level fields expected by frontend
    active_prov = settings.get("active_provider", "gemini")
    masked["current_provider"] = active_prov
    masked["provider"] = active_prov

    ollama_info = settings.get("ollama", {})
    masked["ollama_base_url"] = ollama_info.get("base_url", "http://localhost:11434")
    masked["ollama_model"] = ollama_info.get("model", "")
    masked["base_url"] = masked["ollama_base_url"]
    masked["model_name"] = masked["ollama_model"]

    llamacpp_info = settings.get("llamacpp", {})
    masked["llama_model_path"] = llamacpp_info.get("model_path", "")
    masked["model_path"] = llamacpp_info.get("model_path", "")
    masked["llamacpp_model_path"] = llamacpp_info.get("model_path", "")

    return jsonify(masked)


@app.route("/api/config/save", methods=["POST"])
def config_save():
    """Save provider configuration."""
    data = request.get_json(force=True) or {}
    provider = data.get("provider", "").strip().lower()
    api_key = data.get("api_key", "").strip()

    if not provider:
        return jsonify({"error": "Provider name is required"}), 400

    # Set API key if provided
    if api_key:
        config_manager.set_api_key(provider, api_key)

    # Set active provider
    config_manager.set_active_provider(provider)

    # Handle Ollama settings
    if provider == "ollama":
        base_url = (data.get("base_url") or data.get("ollama_base_url") or "").strip()
        model = (data.get("model_name") or data.get("model") or data.get("ollama_model") or "").strip()
        config_manager.set_ollama_settings(
            base_url=base_url or "http://localhost:11434",
            model=model or "llama3",
        )

    # Handle LlamaCpp settings
    if provider == "llamacpp":
        model_path = (
            data.get("model_path")
            or data.get("llama_model_path")
            or data.get("llamacpp_model_path")
            or ""
        ).strip().strip('"').strip("'")
        if model_path:
            config_manager.set_llamacpp_settings(model_path)

    return jsonify({
        "success": True,
        "active_provider": provider,
        "configured": config_manager.is_configured(),
    })


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSATIONS API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    """List all conversations ordered by most recently updated."""
    conversations = db.get_all_conversations()
    return jsonify(conversations)


@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    """Create a new conversation with uploaded files.

    Expects multipart form data with:
    - title: optional conversation title
    - files: one or more files
    """
    title = request.form.get("title", "").strip()
    files = request.files.getlist("files")

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "At least one file is required to start a conversation"}), 400

    # Process files
    file_names: list[str] = []
    all_text = ""

    # Create upload directory for this conversation
    import uuid as _uuid
    temp_conv_id = str(_uuid.uuid4())
    conv_upload_dir = UPLOAD_BASE_DIR / temp_conv_id
    conv_upload_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        if f.filename == "":
            continue
        try:
            saved_path, extracted_text = file_processor.process_uploaded_file(
                f, str(conv_upload_dir)
            )
            file_names.append(f.filename)
            all_text += f"\n\n--- {f.filename} ---\n{extracted_text}"
        except Exception as e:
            logger.error(f"Failed to process file {f.filename}: {e}")
            return jsonify({"error": f"Failed to process file '{f.filename}': {str(e)}"}), 400

    if not file_names:
        return jsonify({"error": "No valid files were uploaded"}), 400

    # Generate title if not provided
    if not title:
        title = ", ".join(file_names[:3])
        if len(file_names) > 3:
            title += f" (+{len(file_names) - 3} more)"

    # Create conversation in database
    conv_id = db.create_conversation(title=title, file_names=file_names)

    # Rename upload dir to use the real conversation ID
    real_upload_dir = UPLOAD_BASE_DIR / conv_id
    try:
        conv_upload_dir.rename(real_upload_dir)
    except OSError:
        real_upload_dir = conv_upload_dir  # Keep the temp dir if rename fails

    # Index documents in RAG engine
    rag = _get_rag_engine(conv_id)
    chunks = file_processor.chunk_text(all_text)
    metadatas = [{"source": ", ".join(file_names)} for _ in chunks]
    rag.add_documents(texts=chunks, metadatas=metadatas)

    doc_count = rag.get_document_count()
    logger.info(f"Created conversation {conv_id} with {doc_count} chunks from {len(file_names)} files")

    return jsonify({
        "id": conv_id,
        "title": title,
        "file_names": file_names,
        "document_chunks": doc_count,
    }), 201


@app.route("/api/conversations/<conv_id>", methods=["GET"])
def get_conversation(conv_id: str):
    """Get conversation details including messages."""
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(conv)


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def delete_conversation(conv_id: str):
    """Delete a conversation and its vector store."""
    try:
        # Clean up RAG engine
        rag = _get_rag_engine(conv_id)
        rag.delete_collection()
        with _rag_lock:
            _rag_cache.pop(conv_id, None)
    except Exception as e:
        logger.warning(f"Failed to delete RAG collection for {conv_id}: {e}")

    # Delete from database
    deleted = db.delete_conversation(conv_id)
    if not deleted:
        return jsonify({"error": "Conversation not found"}), 404

    # Clean up uploaded files
    upload_dir = UPLOAD_BASE_DIR / conv_id
    if upload_dir.exists():
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)

    return jsonify({"success": True})


@app.route("/api/conversations/<conv_id>/title", methods=["PUT"])
def update_title(conv_id: str):
    """Update conversation title."""
    data = request.get_json(force=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    updated = db.update_conversation_title(conv_id, title)
    if not updated:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"success": True, "title": title})


@app.route("/api/conversations/<conv_id>/files", methods=["POST"])
def add_files(conv_id: str):
    """Add more files to an existing conversation."""
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files provided"}), 400

    conv_upload_dir = UPLOAD_BASE_DIR / conv_id
    conv_upload_dir.mkdir(parents=True, exist_ok=True)

    new_files: list[str] = []
    all_text = ""

    for f in files:
        if f.filename == "":
            continue
        try:
            saved_path, extracted_text = file_processor.process_uploaded_file(
                f, str(conv_upload_dir)
            )
            new_files.append(f.filename)
            all_text += f"\n\n--- {f.filename} ---\n{extracted_text}"
        except Exception as e:
            logger.error(f"Failed to process additional file {f.filename}: {e}")

    if new_files:
        # Update file names in conversation
        existing_files = conv.get("file_names", [])
        if isinstance(existing_files, str):
            try:
                existing_files = json.loads(existing_files)
            except Exception:
                existing_files = []
        updated_files = existing_files + new_files

        # Update DB with new file names
        from database import Database as _DB
        _db = Database()
        with _db.get_connection() as conn:
            conn.execute(
                "UPDATE conversations SET file_names = ?, updated_at = ? WHERE id = ?",
                (json.dumps(updated_files), datetime.utcnow().isoformat(), conv_id),
            )

        # Add to RAG engine
        rag = _get_rag_engine(conv_id)
        chunks = file_processor.chunk_text(all_text)
        metadatas = [{"source": ", ".join(new_files)} for _ in chunks]
        rag.add_documents(texts=chunks, metadatas=metadatas)

    return jsonify({
        "success": True,
        "new_files": new_files,
        "document_chunks": _get_rag_engine(conv_id).get_document_count(),
    })


@app.route("/api/conversations/<conv_id>/chat", methods=["POST"])
def chat(conv_id: str):
    """Send a chat message and get AI response (with streaming via Socket.IO).

    Request body: { "message": "...", "sid": "socket_id" }
    """
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(force=True) or {}
    user_message = data.get("message", "").strip()
    sid = data.get("sid", "")

    if not user_message:
        return jsonify({"error": "Message cannot be empty"}), 400

    # Save user message
    db.add_message(conv_id, role="user", content=user_message, message_type="chat")

    # Start streaming response in background thread
    def generate_response():
        try:
            rag = _get_rag_engine(conv_id)
            context = rag.get_context_for_query(user_message)
            system_prompt, augmented_prompt = rag.build_rag_prompt(user_message, context)

            provider = _get_llm_provider()
            full_response = ""

            for chunk in provider.generate_stream(
                prompt=augmented_prompt,
                system_prompt=system_prompt,
                max_tokens=4096,
            ):
                full_response += chunk
                socketio.emit("response_chunk", {"chunk": chunk, "conversation_id": conv_id}, to=sid)

            # Save assistant message
            db.add_message(conv_id, role="assistant", content=full_response, message_type="chat")
            socketio.emit("response_complete", {
                "conversation_id": conv_id,
                "full_response": full_response,
            }, to=sid)

        except LLMError as e:
            logger.error(f"LLM error: {e}")
            socketio.emit("error", {"message": str(e), "conversation_id": conv_id}, to=sid)
        except Exception as e:
            logger.error(f"Chat error: {traceback.format_exc()}")
            socketio.emit("error", {"message": f"An error occurred: {str(e)}", "conversation_id": conv_id}, to=sid)

    thread = threading.Thread(target=generate_response, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Streaming started"})


@app.route("/api/conversations/<conv_id>/study-material", methods=["POST"])
def generate_study_material(conv_id: str):
    """Generate a Study Material PDF from conversation context."""
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(force=True) or {}
    topics = data.get("topics", "").strip()
    output_dir = data.get("output_dir", "").strip()
    sid = data.get("sid", "")

    if not output_dir:
        output_dir = str(Path.home() / "Documents" / "StudyBuddy")

    def generate():
        try:
            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 10,
                "message": "Retrieving context from documents...",
            }, to=sid)

            rag = _get_rag_engine(conv_id)

            # Get comprehensive context
            query = topics if topics else "Summarize all major topics and concepts"
            context = rag.get_context_for_query(query, n_results=15)

            if not context:
                socketio.emit("error", {
                    "message": "No relevant context found in the uploaded documents.",
                    "conversation_id": conv_id,
                }, to=sid)
                return

            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 30,
                "message": "Generating study material content with AI...",
            }, to=sid)

            system_prompt = get_study_material_prompt(topics if topics else None)
            provider = _get_llm_provider()

            prompt = f"Based on the following source material, create comprehensive study material.\n\nSource Material:\n{context}"
            if topics:
                prompt += f"\n\nFocus on these topics: {topics}"

            content = provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=8192,
            )

            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 70,
                "message": "Generating PDF document...",
            }, to=sid)

            # Generate PDF
            title = conv.get("title", "Study Material")
            output_path = pdf_generator.generate_study_material(
                content=content,
                title=title,
                output_path=output_dir,
            )

            # Record in database
            file_name = Path(output_path).name
            db.add_generated_file(conv_id, file_name, output_path, "study_material")

            # Save in chat history
            db.add_message(
                conv_id,
                role="assistant",
                content=f"📚 Study Material PDF generated successfully!\n\nSaved to: `{output_path}`",
                message_type="study_material",
            )

            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 100,
                "message": "PDF generated successfully!",
            }, to=sid)

            socketio.emit("generation_complete", {
                "conversation_id": conv_id,
                "file_type": "study_material",
                "file_name": file_name,
                "file_path": output_path,
            }, to=sid)

        except LLMError as e:
            logger.error(f"Study material generation LLM error: {e}")
            socketio.emit("error", {"message": str(e), "conversation_id": conv_id}, to=sid)
        except Exception as e:
            logger.error(f"Study material generation error: {traceback.format_exc()}")
            socketio.emit("error", {
                "message": f"Failed to generate study material: {str(e)}",
                "conversation_id": conv_id,
            }, to=sid)

    thread = threading.Thread(target=generate, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "Study material generation started"})


@app.route("/api/conversations/<conv_id>/question-paper", methods=["POST"])
def generate_question_paper(conv_id: str):
    """Generate a Question Paper PDF from conversation context."""
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(force=True) or {}
    topics = data.get("topics", "").strip()
    output_dir = data.get("output_dir", "").strip()
    sid = data.get("sid", "")

    if not output_dir:
        output_dir = str(Path.home() / "Documents" / "StudyBuddy")

    def generate():
        try:
            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 10,
                "message": "Retrieving context from documents...",
            }, to=sid)

            rag = _get_rag_engine(conv_id)

            query = topics if topics else "Cover all major topics and key concepts"
            context = rag.get_context_for_query(query, n_results=15)

            if not context:
                socketio.emit("error", {
                    "message": "No relevant context found in the uploaded documents.",
                    "conversation_id": conv_id,
                }, to=sid)
                return

            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 30,
                "message": "Generating questions and answers with AI...",
            }, to=sid)

            system_prompt = get_question_paper_prompt(topics if topics else None)
            provider = _get_llm_provider()

            prompt = f"Based on the following source material, create a comprehensive question paper with answers.\n\nSource Material:\n{context}"
            if topics:
                prompt += f"\n\nFocus on these topics: {topics}"

            content = provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=8192,
            )

            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 70,
                "message": "Generating PDF document...",
            }, to=sid)

            title = conv.get("title", "Question Paper")
            output_path = pdf_generator.generate_question_paper(
                content=content,
                title=title,
                output_path=output_dir,
            )

            file_name = Path(output_path).name
            db.add_generated_file(conv_id, file_name, output_path, "question_paper")

            db.add_message(
                conv_id,
                role="assistant",
                content=f"📝 Question Paper PDF generated successfully!\n\nSaved to: `{output_path}`",
                message_type="question_paper",
            )

            socketio.emit("generation_progress", {
                "conversation_id": conv_id,
                "progress": 100,
                "message": "PDF generated successfully!",
            }, to=sid)

            socketio.emit("generation_complete", {
                "conversation_id": conv_id,
                "file_type": "question_paper",
                "file_name": file_name,
                "file_path": output_path,
            }, to=sid)

        except LLMError as e:
            logger.error(f"Question paper generation LLM error: {e}")
            socketio.emit("error", {"message": str(e), "conversation_id": conv_id}, to=sid)
        except Exception as e:
            logger.error(f"Question paper generation error: {traceback.format_exc()}")
            socketio.emit("error", {
                "message": f"Failed to generate question paper: {str(e)}",
                "conversation_id": conv_id,
            }, to=sid)

    thread = threading.Thread(target=generate, daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "Question paper generation started"})


@app.route("/api/conversations/<conv_id>/generated-files", methods=["GET"])
def list_generated_files(conv_id: str):
    """List all generated files for a conversation."""
    files = db.get_generated_files(conv_id)
    return jsonify(files)


# ═══════════════════════════════════════════════════════════════════════════
# SOCKET.IO EVENTS
# ═══════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"sid": request.sid})


@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("ping_server")
def handle_ping():
    emit("pong", {"status": "ok"})


# ═══════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum upload size is 100 MB."}), 413


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {traceback.format_exc()}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
