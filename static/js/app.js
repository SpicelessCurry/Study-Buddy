/**
 * Study Buddy - Frontend Application Logic
 * Modern RAG-powered study assistant single-page application.
 */

// ============================================================================
// State Management
// ============================================================================
const AppState = {
    currentConversationId: null,
    conversations: [],
    isConfigured: false,
    isStreaming: false,
    selectedUploadFiles: [], // Queue for new conversation files
    currentStreamingMessageEl: null,
    currentStreamingRawText: '',
    activeFeatureType: 'study-material', // 'study-material' or 'question-paper'
    socket: null,
    defaultOutputDir: 'C:\\Users\\StudyBuddy\\Documents\\StudyBuddy_Exports'
};

// ============================================================================
// Initialization & Socket.IO Setup
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    initMarkdown();
    initSocket();
    initEventListeners();
    checkAppConfiguration();
});

/**
 * Configure marked.js with highlight.js syntax highlighting
 */
function initMarkdown() {
    if (window.marked) {
        window.marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: false,
            mangle: false,
            highlight: function (code, lang) {
                if (window.hljs) {
                    if (lang && window.hljs.getLanguage(lang)) {
                        try {
                            return window.hljs.highlight(code, { language: lang }).value;
                        } catch (err) {
                            console.error('Highlight error:', err);
                        }
                    }
                    try {
                        return window.hljs.highlightAuto(code).value;
                    } catch (err) {
                        return code;
                    }
                }
                return code;
            }
        });
    }
}

/**
 * Initialize Socket.IO connection and register real-time event listeners
 */
function initSocket() {
    try {
        if (typeof io !== 'undefined') {
            AppState.socket = io({
                transports: ['websocket', 'polling'],
                reconnectionAttempts: 5,
                reconnectionDelay: 1000
            });

            AppState.socket.on('connect', () => {
                console.log('Socket.IO connected. ID:', AppState.socket.id);
                if (AppState.currentConversationId) {
                    AppState.socket.emit('join', { conversation_id: AppState.currentConversationId });
                }
            });

            AppState.socket.on('disconnect', (reason) => {
                console.warn('Socket.IO disconnected:', reason);
            });

            AppState.socket.on('connect_error', (error) => {
                console.error('Socket.IO connection error:', error);
            });

            // Streaming assistant response chunk
            AppState.socket.on('response_chunk', (data) => {
                handleResponseChunk(data);
            });

            // Streaming assistant response completion
            AppState.socket.on('response_complete', (data) => {
                handleResponseComplete(data);
            });

            // Backend error message
            AppState.socket.on('error', (data) => {
                console.error('Socket error event:', data);
                const msg = typeof data === 'string' ? data : (data.message || data.error || 'Server error occurred');
                showToast(msg, 'error');
                hideTypingIndicator();
                setStreamingState(false);
            });

            // Generation progress (Study Material / Question Paper)
            AppState.socket.on('generation_progress', (data) => {
                handleGenerationProgress(data);
            });

            // Generation complete
            AppState.socket.on('generation_complete', (data) => {
                handleGenerationComplete(data);
            });
        } else {
            console.warn('Socket.io library not detected.');
        }
    } catch (err) {
        console.error('Failed to initialize Socket.IO:', err);
    }
}

// ============================================================================
// Event Listeners Binding
// ============================================================================
function initEventListeners() {
    // Navigation / Sidebar
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
    const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const newConversationBtn = document.getElementById('newConversationBtn');
    const welcomeNewChatBtn = document.getElementById('welcomeNewChatBtn');
    const conversationSearchInput = document.getElementById('conversationSearchInput');
    const clearSearchBtn = document.getElementById('clearSearchBtn');

    if (sidebarToggleBtn) sidebarToggleBtn.addEventListener('click', toggleSidebar);
    if (sidebarCloseBtn) sidebarCloseBtn.addEventListener('click', toggleSidebar);
    if (sidebarOverlay) sidebarOverlay.addEventListener('click', toggleSidebar);

    if (newConversationBtn) {
        newConversationBtn.addEventListener('click', () => showUploadScreen());
    }
    if (welcomeNewChatBtn) {
        welcomeNewChatBtn.addEventListener('click', () => showUploadScreen());
    }

    if (conversationSearchInput) {
        conversationSearchInput.addEventListener('input', (e) => {
            const query = e.target.value;
            searchConversations(query);
            if (clearSearchBtn) {
                clearSearchBtn.classList.toggle('hidden', query.trim().length === 0);
            }
        });
    }

    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', () => {
            if (conversationSearchInput) {
                conversationSearchInput.value = '';
                searchConversations('');
                clearSearchBtn.classList.add('hidden');
                conversationSearchInput.focus();
            }
        });
    }

    // Settings Modal Triggers
    const sidebarSettingsBtn = document.getElementById('sidebarSettingsBtn');
    const topBarSettingsBtn = document.getElementById('topBarSettingsBtn');
    const closeSettingsBtn = document.getElementById('closeSettingsBtn');
    const cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    const settingsProviderSelect = document.getElementById('settingsProviderSelect');

    if (sidebarSettingsBtn) sidebarSettingsBtn.addEventListener('click', showSettingsModal);
    if (topBarSettingsBtn) topBarSettingsBtn.addEventListener('click', showSettingsModal);
    if (closeSettingsBtn) closeSettingsBtn.addEventListener('click', hideSettingsModal);
    if (cancelSettingsBtn) cancelSettingsBtn.addEventListener('click', hideSettingsModal);
    if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', handleSaveSettings);

    if (settingsProviderSelect) {
        settingsProviderSelect.addEventListener('change', (e) => {
            toggleProviderFields(e.target.value, 'settings');
        });
    }

    // Setup Modal Triggers
    const setupProviderSelect = document.getElementById('setupProviderSelect');
    const saveSetupBtn = document.getElementById('saveSetupBtn');

    if (setupProviderSelect) {
        setupProviderSelect.addEventListener('change', (e) => {
            toggleProviderFields(e.target.value, 'setup');
        });
    }
    if (saveSetupBtn) {
        saveSetupBtn.addEventListener('click', handleSaveSetup);
    }

    // Password visibility toggles
    document.querySelectorAll('.toggle-password-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (input) {
                const isPassword = input.type === 'password';
                input.type = isPassword ? 'text' : 'password';
                btn.innerHTML = isPassword ? '<i class="fa-solid fa-eye-slash"></i>' : '<i class="fa-solid fa-eye"></i>';
            }
        });
    });

    // File Upload Screen Handlers
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const browseFilesBtn = document.getElementById('browseFilesBtn');
    const cancelUploadBtn = document.getElementById('cancelUploadBtn');
    const startConversationBtn = document.getElementById('startConversationBtn');
    const clearAllFilesBtn = document.getElementById('clearAllFilesBtn');

    if (browseFilesBtn && fileInput) {
        browseFilesBtn.addEventListener('click', () => fileInput.click());
    }

    if (dropZone && fileInput) {
        dropZone.addEventListener('click', (e) => {
            if (e.target !== browseFilesBtn && !browseFilesBtn.contains(e.target)) {
                fileInput.click();
            }
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            handleFileDrop(e);
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                addFilesToQueue(Array.from(e.target.files));
                fileInput.value = '';
            }
        });
    }

    if (clearAllFilesBtn) {
        clearAllFilesBtn.addEventListener('click', () => {
            AppState.selectedUploadFiles = [];
            renderSelectedFilesQueue();
        });
    }

    if (cancelUploadBtn) {
        cancelUploadBtn.addEventListener('click', () => {
            AppState.selectedUploadFiles = [];
            renderSelectedFilesQueue();
            if (AppState.currentConversationId) {
                showChatScreen();
            } else if (AppState.conversations.length > 0) {
                selectConversation(AppState.conversations[0].id);
            } else {
                showWelcomeScreen();
            }
        });
    }

    if (startConversationBtn) {
        startConversationBtn.addEventListener('click', handleCreateConversation);
    }

    // Active Chat & Messaging
    const chatTextarea = document.getElementById('chatTextarea');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const attachMoreFilesBtn = document.getElementById('attachMoreFilesBtn');
    const attachMoreFileInput = document.getElementById('attachMoreFileInput');

    if (chatTextarea) {
        chatTextarea.addEventListener('input', () => {
            // Auto expand textarea height
            chatTextarea.style.height = 'auto';
            const newHeight = Math.min(chatTextarea.scrollHeight, 160);
            chatTextarea.style.height = `${newHeight}px`;

            // Enable/disable send button
            if (sendChatBtn) {
                sendChatBtn.disabled = !chatTextarea.value.trim() || AppState.isStreaming;
            }
        });

        chatTextarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!AppState.isStreaming && chatTextarea.value.trim()) {
                    handleSendMessage();
                }
            }
        });
    }

    if (sendChatBtn) {
        sendChatBtn.addEventListener('click', handleSendMessage);
    }

    if (attachMoreFilesBtn && attachMoreFileInput) {
        attachMoreFilesBtn.addEventListener('click', () => attachMoreFileInput.click());
        attachMoreFileInput.addEventListener('change', handleAttachMoreFiles);
    }

    // Editable Conversation Title
    const activeConversationTitle = document.getElementById('activeConversationTitle');
    const renameTitleBtn = document.getElementById('renameTitleBtn');
    const titleEditInput = document.getElementById('titleEditInput');

    if (renameTitleBtn) {
        renameTitleBtn.addEventListener('click', enableTitleEditing);
    }
    if (activeConversationTitle) {
        activeConversationTitle.addEventListener('click', enableTitleEditing);
    }
    if (titleEditInput) {
        titleEditInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                saveConversationTitle();
            } else if (e.key === 'Escape') {
                cancelTitleEditing();
            }
        });
        titleEditInput.addEventListener('blur', saveConversationTitle);
    }

    // Feature Generation (Study Material & Question Paper)
    const studyMaterialBtn = document.getElementById('studyMaterialBtn');
    const questionPaperBtn = document.getElementById('questionPaperBtn');
    const generatedFilesBtn = document.getElementById('generatedFilesBtn');
    const closeFeatureModalBtn = document.getElementById('closeFeatureModalBtn');
    const cancelFeatureBtn = document.getElementById('cancelFeatureBtn');
    const submitFeatureBtn = document.getElementById('submitFeatureBtn');
    const resetDefaultDirBtn = document.getElementById('resetDefaultDirBtn');

    if (studyMaterialBtn) {
        studyMaterialBtn.addEventListener('click', () => showFeatureModal('study-material'));
    }
    if (questionPaperBtn) {
        questionPaperBtn.addEventListener('click', () => showFeatureModal('question-paper'));
    }
    if (generatedFilesBtn) {
        generatedFilesBtn.addEventListener('click', showGeneratedFilesModal);
    }
    if (closeFeatureModalBtn) closeFeatureModalBtn.addEventListener('click', hideFeatureModal);
    if (cancelFeatureBtn) cancelFeatureBtn.addEventListener('click', hideFeatureModal);
    if (submitFeatureBtn) submitFeatureBtn.addEventListener('click', handleSubmitFeature);

    if (resetDefaultDirBtn) {
        resetDefaultDirBtn.addEventListener('click', () => {
            const outInput = document.getElementById('featureOutputDirInput');
            if (outInput) outInput.value = AppState.defaultOutputDir;
        });
    }

    // Attached Files Modal
    const viewFilesBtn = document.getElementById('viewFilesBtn');
    const closeFilesModalBtn = document.getElementById('closeFilesModalBtn');
    const closeFilesModalBottomBtn = document.getElementById('closeFilesModalBottomBtn');
    const modalAttachMoreBtn = document.getElementById('modalAttachMoreBtn');

    if (viewFilesBtn) viewFilesBtn.addEventListener('click', showAttachedFilesModal);
    if (closeFilesModalBtn) closeFilesModalBtn.addEventListener('click', hideAttachedFilesModal);
    if (closeFilesModalBottomBtn) closeFilesModalBottomBtn.addEventListener('click', hideAttachedFilesModal);
    if (modalAttachMoreBtn && attachMoreFileInput) {
        modalAttachMoreBtn.addEventListener('click', () => {
            hideAttachedFilesModal();
            attachMoreFileInput.click();
        });
    }

    // Generated Files Modal Close
    const closeGeneratedFilesModalBtn = document.getElementById('closeGeneratedFilesModalBtn');
    const closeGeneratedFilesModalBottomBtn = document.getElementById('closeGeneratedFilesModalBottomBtn');
    if (closeGeneratedFilesModalBtn) closeGeneratedFilesModalBtn.addEventListener('click', hideGeneratedFilesModal);
    if (closeGeneratedFilesModalBottomBtn) closeGeneratedFilesModalBottomBtn.addEventListener('click', hideGeneratedFilesModal);
}

// ============================================================================
// Config & Settings Management
// ============================================================================

/**
 * Checks backend configuration status on load
 */
async function checkAppConfiguration() {
    try {
        const response = await fetch('/api/config/status');
        if (!response.ok) {
            throw new Error(`Status check failed: ${response.status}`);
        }
        const data = await response.json();
        AppState.isConfigured = !!data.configured;

        if (data.configured) {
            // Already configured: keep setup modal hidden and open directly to workspace
            hideSetupModal();
            const activeProvider = data.active_provider || data.provider || 'Ready';
            updateSidebarProviderDisplay(activeProvider);
            loadConversations();
        } else {
            // First time running: show setup modal
            showSetupModal();
        }
    } catch (err) {
        console.error('Failed to verify app configuration:', err);
        // Fallback: show setup modal to allow user to configure
        showSetupModal();
    }
}

/**
 * Toggles provider specific form fields
 */
function toggleProviderFields(provider, modalType) {
    const isSetup = modalType === 'setup';
    const prefix = isSetup ? 'setup' : 'settings';

    const apiKeyGroup = document.getElementById(`${prefix}ApiKeyGroup`);
    const ollamaGroup = document.getElementById(`${prefix}OllamaGroup`);
    const llamaCppGroup = document.getElementById(`${prefix}LlamaCppGroup`);

    if (!apiKeyGroup || !ollamaGroup || !llamaCppGroup) return;

    if (provider === 'ollama') {
        apiKeyGroup.classList.add('hidden');
        ollamaGroup.classList.remove('hidden');
        llamaCppGroup.classList.add('hidden');
    } else if (provider === 'llamacpp') {
        apiKeyGroup.classList.add('hidden');
        ollamaGroup.classList.add('hidden');
        llamaCppGroup.classList.remove('hidden');
    } else {
        // Cloud providers: gemini, openai, claude
        apiKeyGroup.classList.remove('hidden');
        ollamaGroup.classList.add('hidden');
        llamaCppGroup.classList.add('hidden');

        // Dynamic placeholder if API key is already configured
        const apiKeyInput = document.getElementById(`${prefix}ApiKeyInput`);
        if (apiKeyInput) {
            if (modalType === 'settings' && AppState.apiKeys && AppState.apiKeys[provider]) {
                apiKeyInput.placeholder = `Key saved (${AppState.apiKeys[provider]}) - leave blank to keep`;
            } else {
                apiKeyInput.placeholder = `Enter your ${formatProviderName(provider)} API key`;
            }
        }
    }
}

function showSetupModal() {
    const modal = document.getElementById('setupModal');
    if (modal) {
        modal.classList.remove('hidden');
        const providerSelect = document.getElementById('setupProviderSelect');
        if (providerSelect) {
            toggleProviderFields(providerSelect.value, 'setup');
        }
    }
}

function hideSetupModal() {
    const modal = document.getElementById('setupModal');
    if (modal) modal.classList.add('hidden');
}

/**
 * Handle initial setup form submission
 */
async function handleSaveSetup() {
    const provider = document.getElementById('setupProviderSelect').value;
    const apiKey = document.getElementById('setupApiKeyInput').value.trim();
    const ollamaBaseUrl = document.getElementById('setupOllamaBaseUrl').value.trim();
    const ollamaModelName = document.getElementById('setupOllamaModelName').value.trim();
    const llamaModelPath = document.getElementById('setupLlamaModelPath').value.trim();

    const payload = { provider };

    if (provider === 'ollama') {
        if (!ollamaBaseUrl) {
            showToast('Please provide the Ollama Base URL', 'warning');
            return;
        }
        payload.base_url = ollamaBaseUrl;
        payload.model_name = ollamaModelName || 'llama3.2';
    } else if (provider === 'llamacpp') {
        if (!llamaModelPath) {
            showToast('Please specify the path to your GGUF model', 'warning');
            return;
        }
        payload.model_path = llamaModelPath;
    } else {
        if (!apiKey) {
            showToast('Please enter an API key for the selected provider', 'warning');
            return;
        }
        payload.api_key = apiKey;
    }

    try {
        const response = await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to save configuration');
        }

        AppState.isConfigured = true;
        hideSetupModal();
        updateSidebarProviderDisplay(provider);
        showToast('Configuration saved successfully!', 'success');
        loadConversations();
    } catch (err) {
        console.error('Error saving config:', err);
        showToast(err.message, 'error');
    }
}

/**
 * Shows the Settings modal and populates current configuration
 */
async function showSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (!modal) return;

    try {
        const response = await fetch('/api/config/settings');
        if (response.ok) {
            const data = await response.json();
            AppState.apiKeys = data.api_keys || {};
            const currentProvider = data.current_provider || data.provider || 'gemini';
            const label = document.getElementById('settingsActiveProviderLabel');
            if (label) label.textContent = formatProviderName(currentProvider);

            const select = document.getElementById('settingsProviderSelect');
            if (select) {
                select.value = currentProvider;
                toggleProviderFields(currentProvider, 'settings');
            }

            const apiKeyInput = document.getElementById('settingsApiKeyInput');
            if (apiKeyInput) apiKeyInput.value = '';

            if (data.ollama_base_url) {
                const ollamaBase = document.getElementById('settingsOllamaBaseUrl');
                if (ollamaBase) ollamaBase.value = data.ollama_base_url;
            }
            if (data.ollama_model) {
                const ollamaModel = document.getElementById('settingsOllamaModelName');
                if (ollamaModel) ollamaModel.value = data.ollama_model;
            }
            if (data.llama_model_path) {
                const llamaPath = document.getElementById('settingsLlamaModelPath');
                if (llamaPath) llamaPath.value = data.llama_model_path;
            }
        }
    } catch (err) {
        console.warn('Could not fetch settings details:', err);
    }

    modal.classList.remove('hidden');
}

function hideSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) modal.classList.add('hidden');
}

/**
 * Handle settings form update
 */
async function handleSaveSettings() {
    const provider = document.getElementById('settingsProviderSelect').value;
    const apiKey = document.getElementById('settingsApiKeyInput').value.trim();
    const ollamaBaseUrl = document.getElementById('settingsOllamaBaseUrl').value.trim();
    const ollamaModelName = document.getElementById('settingsOllamaModelName').value.trim();
    const llamaModelPath = document.getElementById('settingsLlamaModelPath').value.trim();

    const payload = { provider };
    if (apiKey) payload.api_key = apiKey;
    if (provider === 'ollama') {
        if (ollamaBaseUrl) payload.base_url = ollamaBaseUrl;
        if (ollamaModelName) payload.model_name = ollamaModelName;
    } else if (provider === 'llamacpp') {
        if (llamaModelPath) payload.model_path = llamaModelPath;
    }

    try {
        const response = await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to update settings');
        }

        hideSettingsModal();
        updateSidebarProviderDisplay(provider);
        showToast('Settings updated successfully!', 'success');
    } catch (err) {
        console.error('Error saving settings:', err);
        showToast(err.message, 'error');
    }
}

function updateSidebarProviderDisplay(providerName) {
    const pill = document.getElementById('sidebarProviderName');
    if (pill) {
        pill.textContent = formatProviderName(providerName);
    }
}

function formatProviderName(code) {
    const map = {
        'gemini': 'Gemini',
        'openai': 'OpenAI',
        'claude': 'Claude',
        'ollama': 'Ollama',
        'llamacpp': 'LlamaCpp'
    };
    return map[code?.toLowerCase()] || code || 'Configured';
}

// ============================================================================
// Conversations Sidebar & Navigation
// ============================================================================

/**
 * Loads all conversations from backend and renders sidebar list
 */
async function loadConversations() {
    try {
        const response = await fetch('/api/conversations');
        if (!response.ok) {
            throw new Error(`Failed to load conversations: ${response.status}`);
        }
        const data = await response.json();
        AppState.conversations = Array.isArray(data) ? data : (data.conversations || []);
        renderConversationList(AppState.conversations);

        // Update badge count
        const countBadge = document.getElementById('conversationCountBadge');
        if (countBadge) {
            countBadge.textContent = AppState.conversations.length;
        }

        // If no active conversation, select the first or show welcome screen
        if (!AppState.currentConversationId) {
            if (AppState.conversations.length > 0) {
                selectConversation(AppState.conversations[0].id);
            } else {
                showWelcomeScreen();
            }
        }
    } catch (err) {
        console.error('Error loading conversations:', err);
        showToast('Failed to load conversation history', 'error');
        showWelcomeScreen();
    }
}

/**
 * Renders conversation items inside the sidebar
 */
function renderConversationList(list) {
    const container = document.getElementById('conversationList');
    const emptyPlaceholder = document.getElementById('noConversationsMsg');
    if (!container) return;

    container.innerHTML = '';

    if (!list || list.length === 0) {
        if (emptyPlaceholder) emptyPlaceholder.classList.remove('hidden');
        return;
    }

    if (emptyPlaceholder) emptyPlaceholder.classList.add('hidden');

    list.forEach(conv => {
        const item = document.createElement('div');
        item.className = `conversation-item ${conv.id === AppState.currentConversationId ? 'active' : ''}`;
        item.setAttribute('data-id', conv.id);

        const dateStr = formatDate(conv.updated_at || conv.created_at);
        const filesCount = conv.file_count || (conv.files ? conv.files.length : 0);

        item.innerHTML = `
            <div class="conversation-info">
                <div class="conversation-title-text" title="${escapeHtml(conv.title || 'Untitled Session')}">
                    ${escapeHtml(conv.title || 'Untitled Session')}
                </div>
                <div class="conversation-meta">
                    <span class="conversation-files-count">
                        <i class="fa-regular fa-file"></i> ${filesCount}
                    </span>
                    <span>•</span>
                    <span>${dateStr}</span>
                </div>
            </div>
            <div class="conversation-actions">
                <button class="delete-conv-btn" title="Delete conversation" data-id="${conv.id}">
                    <i class="fa-regular fa-trash-can"></i>
                </button>
            </div>
        `;

        // Click to select
        item.addEventListener('click', (e) => {
            if (e.target.closest('.delete-conv-btn')) return;
            selectConversation(conv.id);
            if (window.innerWidth <= 768) {
                toggleSidebar();
            }
        });

        // Click delete
        const delBtn = item.querySelector('.delete-conv-btn');
        if (delBtn) {
            delBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                handleDeleteConversation(conv.id, conv.title);
            });
        }

        container.appendChild(item);
    });
}

/**
 * Selects an active conversation and loads its messages
 */
async function selectConversation(id) {
    if (AppState.currentConversationId === id) return;

    AppState.currentConversationId = id;

    // Join Socket room for this conversation
    if (AppState.socket && AppState.socket.connected) {
        AppState.socket.emit('join', { conversation_id: id });
    }

    // Update active highlight in sidebar
    document.querySelectorAll('.conversation-item').forEach(el => {
        el.classList.toggle('active', el.getAttribute('data-id') === String(id));
    });

    try {
        const response = await fetch(`/api/conversations/${id}`);
        if (!response.ok) {
            throw new Error(`Failed to load conversation: ${response.status}`);
        }
        const data = await response.json();
        const conv = data.conversation || data;

        // Update Top Bar Title
        updateTopBarTitle(conv.title || 'Study Buddy Session');

        // Update Attached Files Badge
        updateAttachedFilesBadge(conv.files || []);

        // Render Messages
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {
            chatMessages.innerHTML = '';
            const messages = conv.messages || [];
            if (messages.length === 0) {
                // Initial greeting from assistant
                appendMessage('assistant', `Hello! I have loaded your study materials for **${conv.title || 'this session'}**. Ask me questions, request explanations, or use the AI tools above to generate study guides!`);
            } else {
                messages.forEach(msg => {
                    appendMessage(msg.role, msg.content, msg.type, msg.timestamp || msg.created_at);
                });
            }
        }

        showChatScreen();
        scrollChatToBottom();
    } catch (err) {
        console.error('Error fetching conversation:', err);
        showToast('Error loading conversation details', 'error');
    }
}

/**
 * Filter conversations in sidebar
 */
function searchConversations(query) {
    const q = query.trim().toLowerCase();
    if (!q) {
        renderConversationList(AppState.conversations);
        return;
    }

    const filtered = AppState.conversations.filter(c => {
        return (c.title && c.title.toLowerCase().includes(q));
    });

    renderConversationList(filtered);
}

/**
 * Deletes a conversation
 */
async function handleDeleteConversation(id, title) {
    if (!confirm(`Are you sure you want to delete "${title || 'this conversation'}"?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/conversations/${id}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete conversation');
        }

        showToast('Conversation deleted', 'info');

        // Remove from local state
        AppState.conversations = AppState.conversations.filter(c => c.id !== id);

        // Update sidebar count
        const countBadge = document.getElementById('conversationCountBadge');
        if (countBadge) countBadge.textContent = AppState.conversations.length;

        // If the deleted conversation was active
        if (AppState.currentConversationId === id) {
            AppState.currentConversationId = null;
            if (AppState.conversations.length > 0) {
                selectConversation(AppState.conversations[0].id);
            } else {
                showWelcomeScreen();
            }
        }

        renderConversationList(AppState.conversations);
    } catch (err) {
        console.error('Delete conversation error:', err);
        showToast(err.message, 'error');
    }
}

// ============================================================================
// File Upload & New Conversation Creation
// ============================================================================

function handleFileDrop(e) {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
        addFilesToQueue(Array.from(dt.files));
    }
}

function addFilesToQueue(files) {
    const supportedExtensions = ['.pdf', '.docx', '.doc', '.txt', '.md', '.pptx'];

    let addedCount = 0;
    files.forEach(file => {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (supportedExtensions.includes(ext)) {
            // Check for duplicates in current queue
            const exists = AppState.selectedUploadFiles.some(f => f.name === file.name && f.size === file.size);
            if (!exists) {
                AppState.selectedUploadFiles.push(file);
                addedCount++;
            }
        } else {
            showToast(`Skipped unsupported file: ${file.name}`, 'warning');
        }
    });

    if (addedCount > 0) {
        renderSelectedFilesQueue();
    }
}

function renderSelectedFilesQueue() {
    const queueSection = document.getElementById('selectedFilesSection');
    const queueList = document.getElementById('selectedFilesList');
    const countEl = document.getElementById('selectedFilesCount');
    const startBtn = document.getElementById('startConversationBtn');

    if (!queueSection || !queueList) return;

    const files = AppState.selectedUploadFiles;
    if (countEl) countEl.textContent = files.length;

    if (files.length === 0) {
        queueSection.classList.add('hidden');
        if (startBtn) startBtn.disabled = true;
        queueList.innerHTML = '';
        return;
    }

    queueSection.classList.remove('hidden');
    if (startBtn) startBtn.disabled = false;
    queueList.innerHTML = '';

    files.forEach((file, index) => {
        const li = document.createElement('li');
        li.className = 'selected-file-item';

        const sizeFormatted = formatFileSize(file.size);
        const iconClass = getFileIcon(file.name);

        li.innerHTML = `
            <div class="selected-file-name" title="${escapeHtml(file.name)}">
                <i class="${iconClass}"></i>
                <span>${escapeHtml(file.name)}</span>
                <span class="selected-file-size">(${sizeFormatted})</span>
            </div>
            <button class="remove-file-btn" data-index="${index}" title="Remove file">
                <i class="fa-solid fa-xmark"></i>
            </button>
        `;

        li.querySelector('.remove-file-btn').addEventListener('click', (e) => {
            const idx = parseInt(e.currentTarget.getAttribute('data-index'), 10);
            AppState.selectedUploadFiles.splice(idx, 1);
            renderSelectedFilesQueue();
        });

        queueList.appendChild(li);
    });
}

/**
 * Creates a new conversation with uploaded files
 */
async function handleCreateConversation() {
    if (AppState.selectedUploadFiles.length === 0) {
        showToast('Please select at least one study material file', 'warning');
        return;
    }

    const titleInput = document.getElementById('newConversationTitleInput');
    const customTitle = titleInput ? titleInput.value.trim() : '';
    const fallbackTitle = AppState.selectedUploadFiles[0].name.replace(/\.[^/.]+$/, '');
    const title = customTitle || fallbackTitle;

    const startBtn = document.getElementById('startConversationBtn');
    const originalText = startBtn ? startBtn.innerHTML : '';
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing Documents...';
    }

    const formData = new FormData();
    formData.append('title', title);
    AppState.selectedUploadFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        const response = await fetch('/api/conversations', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to create conversation');
        }

        const newConv = data.conversation || data;
        showToast('Study session created successfully!', 'success');

        // Clear queue
        AppState.selectedUploadFiles = [];
        if (titleInput) titleInput.value = '';
        renderSelectedFilesQueue();

        // Reload conversation list and switch to the new session
        await loadConversations();
        selectConversation(newConv.id);
    } catch (err) {
        console.error('Error creating conversation:', err);
        showToast(err.message, 'error');
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = originalText;
        }
    }
}

/**
 * Attaches more files to the active conversation
 */
async function handleAttachMoreFiles(e) {
    if (!AppState.currentConversationId) {
        showToast('No active conversation selected', 'warning');
        return;
    }

    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    const formData = new FormData();
    files.forEach(file => {
        formData.append('files', file);
    });

    showToast('Uploading additional files...', 'info');

    try {
        const response = await fetch(`/api/conversations/${AppState.currentConversationId}/files`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to upload additional documents');
        }

        showToast('Documents attached and indexed successfully!', 'success');
        e.target.value = '';

        // Refresh conversation details & sidebar
        await loadConversations();
        selectConversation(AppState.currentConversationId);
    } catch (err) {
        console.error('Error attaching files:', err);
        showToast(err.message, 'error');
    }
}

// ============================================================================
// Messaging & Chat Interaction
// ============================================================================

/**
 * Handles sending user message
 */
async function handleSendMessage() {
    const textarea = document.getElementById('chatTextarea');
    if (!textarea || AppState.isStreaming) return;

    const text = textarea.value.trim();
    if (!text) return;

    if (!AppState.currentConversationId) {
        showToast('Please select or create a conversation first', 'warning');
        return;
    }

    // Add user message to UI
    appendMessage('user', text);

    // Reset textarea
    textarea.value = '';
    textarea.style.height = 'auto';
    const sendBtn = document.getElementById('sendChatBtn');
    if (sendBtn) sendBtn.disabled = true;

    // Show AI typing indicator
    showTypingIndicator();
    setStreamingState(true);

    try {
        const payload = {
            message: text,
            socket_id: AppState.socket ? AppState.socket.id : null
        };

        const response = await fetch(`/api/conversations/${AppState.currentConversationId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to send message');
        }

        const resData = await response.json();

        // If server returns synchronous response instead of socket stream:
        if (resData.response && !AppState.currentStreamingMessageEl) {
            hideTypingIndicator();
            appendMessage('assistant', resData.response);
            setStreamingState(false);
        }
    } catch (err) {
        console.error('Chat error:', err);
        showToast(err.message, 'error');
        hideTypingIndicator();
        setStreamingState(false);
    }
}

/**
 * Appends a message to the chat container
 */
function appendMessage(role, content, type = 'text', timestamp = null) {
    const container = document.getElementById('chatMessages');
    if (!container) return;

    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${role}`;

    const avatarHtml = role === 'user' 
        ? '<div class="message-avatar"><i class="fa-solid fa-user"></i></div>'
        : '<div class="message-avatar"><i class="fa-solid fa-robot"></i></div>';

    const timeStr = timestamp ? formatDate(timestamp, true) : 'Just now';
    const renderedBody = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content).replace(/\n/g, '<br>');

    wrapper.innerHTML = `
        ${avatarHtml}
        <div class="message-bubble-wrapper">
            <div class="message-bubble">
                <div class="message-text">${renderedBody}</div>
            </div>
            <div class="message-meta">${timeStr}</div>
        </div>
    `;

    container.appendChild(wrapper);
    scrollChatToBottom();
    return wrapper;
}

/**
 * Handles incoming streaming chunk from Socket.IO
 */
function handleResponseChunk(data) {
    hideTypingIndicator();

    const chunk = typeof data === 'string' ? data : (data.chunk || '');
    if (!chunk) return;

    if (!AppState.currentStreamingMessageEl) {
        // Create initial streaming bubble
        const container = document.getElementById('chatMessages');
        if (!container) return;

        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper assistant';
        wrapper.innerHTML = `
            <div class="message-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="message-bubble-wrapper">
                <div class="message-bubble">
                    <div class="message-text"></div>
                </div>
                <div class="message-meta">Typing...</div>
            </div>
        `;
        container.appendChild(wrapper);

        AppState.currentStreamingMessageEl = wrapper.querySelector('.message-text');
        AppState.currentStreamingRawText = '';
    }

    AppState.currentStreamingRawText += chunk;
    if (AppState.currentStreamingMessageEl) {
        AppState.currentStreamingMessageEl.innerHTML = renderMarkdown(AppState.currentStreamingRawText);
    }
    scrollChatToBottom();
}

/**
 * Handles completion of streaming response
 */
function handleResponseComplete(data) {
    hideTypingIndicator();

    if (AppState.currentStreamingMessageEl) {
        const fullResponse = data && data.full_response ? data.full_response : AppState.currentStreamingRawText;
        AppState.currentStreamingMessageEl.innerHTML = renderMarkdown(fullResponse);

        // Update meta timestamp
        const meta = AppState.currentStreamingMessageEl.closest('.message-bubble-wrapper')?.querySelector('.message-meta');
        if (meta) meta.textContent = 'Just now';

        AppState.currentStreamingMessageEl = null;
        AppState.currentStreamingRawText = '';
    }

    setStreamingState(false);
    scrollChatToBottom();
}

function setStreamingState(isStreaming) {
    AppState.isStreaming = isStreaming;
    const sendBtn = document.getElementById('sendChatBtn');
    const textarea = document.getElementById('chatTextarea');

    if (sendBtn) {
        sendBtn.disabled = isStreaming || (textarea && !textarea.value.trim());
    }
}

function showTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.classList.remove('hidden');
        scrollChatToBottom();
    }
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.classList.add('hidden');
    }
}

function scrollChatToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// ============================================================================
// Feature Modals (Study Material & Question Paper Generation)
// ============================================================================

function showFeatureModal(type) {
    AppState.activeFeatureType = type;
    const modal = document.getElementById('featureModal');
    const titleEl = document.getElementById('featureModalTitle');
    const subtitleEl = document.getElementById('featureModalSubtitle');
    const iconEl = document.getElementById('featureModalIcon');
    const submitBtnText = document.getElementById('submitFeatureBtnText');
    const outDirInput = document.getElementById('featureOutputDirInput');
    const topicsInput = document.getElementById('featureTopicsInput');
    const progressBox = document.getElementById('featureProgressContainer');

    if (!modal) return;

    if (progressBox) progressBox.classList.add('hidden');
    if (topicsInput) topicsInput.value = '';
    if (outDirInput && !outDirInput.value) {
        outDirInput.value = AppState.defaultOutputDir;
    }

    if (type === 'study-material') {
        if (titleEl) titleEl.textContent = 'Generate Study Material PDF';
        if (subtitleEl) subtitleEl.textContent = 'Synthesize comprehensive study guides, summaries, and key formula/concept sheets from your uploaded documents.';
        if (iconEl) iconEl.className = 'fa-solid fa-book-open modal-icon-small';
        if (submitBtnText) submitBtnText.textContent = 'Generate Study Guide PDF';
    } else {
        if (titleEl) titleEl.textContent = 'Generate Question Paper PDF';
        if (subtitleEl) subtitleEl.textContent = 'Create a tailored mock examination paper with multiple-choice, short-answer, and descriptive questions based on your documents.';
        if (iconEl) iconEl.className = 'fa-solid fa-pen-to-square modal-icon-small';
        if (submitBtnText) submitBtnText.textContent = 'Generate Question Paper PDF';
    }

    modal.classList.remove('hidden');
}

function hideFeatureModal() {
    const modal = document.getElementById('featureModal');
    if (modal) modal.classList.add('hidden');
}

async function handleSubmitFeature() {
    if (!AppState.currentConversationId) {
        showToast('Please open a study session first', 'warning');
        return;
    }

    const type = AppState.activeFeatureType;
    const topics = document.getElementById('featureTopicsInput')?.value.trim() || '';
    const outputDir = document.getElementById('featureOutputDirInput')?.value.trim() || AppState.defaultOutputDir;

    const submitBtn = document.getElementById('submitFeatureBtn');
    const spinner = document.getElementById('featureLoadingSpinner');
    const progressBox = document.getElementById('featureProgressContainer');
    const progressMsg = document.getElementById('featureProgressMessage');
    const progressBar = document.getElementById('featureProgressBar');
    const progressPercent = document.getElementById('featureProgressPercent');

    if (submitBtn) submitBtn.disabled = true;
    if (spinner) spinner.classList.remove('hidden');
    if (progressBox) progressBox.classList.remove('hidden');
    if (progressMsg) progressMsg.textContent = 'Initiating AI generation...';
    if (progressBar) progressBar.style.width = '10%';
    if (progressPercent) progressPercent.textContent = '10%';

    const endpoint = type === 'study-material'
        ? `/api/conversations/${AppState.currentConversationId}/study-material`
        : `/api/conversations/${AppState.currentConversationId}/question-paper`;

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topics: topics,
                output_dir: outputDir,
                socket_id: AppState.socket ? AppState.socket.id : null
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to start generation');
        }

        if (data.file_path || data.filename) {
            handleGenerationComplete({
                filename: data.filename || 'generated_study_document.pdf',
                path: data.file_path || data.path,
                type: type
            });
        }
    } catch (err) {
        console.error('Feature generation error:', err);
        showToast(err.message, 'error');
        if (submitBtn) submitBtn.disabled = false;
        if (spinner) spinner.classList.add('hidden');
    }
}

function handleGenerationProgress(data) {
    const progressBox = document.getElementById('featureProgressContainer');
    const progressMsg = document.getElementById('featureProgressMessage');
    const progressBar = document.getElementById('featureProgressBar');
    const progressPercent = document.getElementById('featureProgressPercent');

    if (progressBox) progressBox.classList.remove('hidden');

    const percent = data.percent || 50;
    const msg = data.message || data.stage || 'Generating document...';

    if (progressMsg) progressMsg.textContent = msg;
    if (progressBar) progressBar.style.width = `${percent}%`;
    if (progressPercent) progressPercent.textContent = `${percent}%`;
}

function handleGenerationComplete(data) {
    const submitBtn = document.getElementById('submitFeatureBtn');
    const spinner = document.getElementById('featureLoadingSpinner');
    if (submitBtn) submitBtn.disabled = false;
    if (spinner) spinner.classList.add('hidden');

    hideFeatureModal();

    const fileName = data.filename || 'Document.pdf';
    const filePath = data.path || data.file_path || '';
    const successMsg = `PDF generated successfully! Saved at: ${filePath || fileName}`;

    showToast(successMsg, 'success');

    // Also notify in chat
    if (AppState.currentConversationId) {
        appendMessage('assistant', `✅ **PDF Generation Complete!**\n\nYour file **${fileName}** has been generated.\n\n*Saved Location:* \`${filePath}\``);
    }
}

// ============================================================================
// Attached Files & Generated Files Modals
// ============================================================================

async function showAttachedFilesModal() {
    if (!AppState.currentConversationId) return;

    const modal = document.getElementById('filesModal');
    const listContainer = document.getElementById('activeFilesList');
    if (!modal || !listContainer) return;

    listContainer.innerHTML = '<li class="active-file-item">Loading session files...</li>';
    modal.classList.remove('hidden');

    try {
        const response = await fetch(`/api/conversations/${AppState.currentConversationId}`);
        const data = await response.json();
        const conv = data.conversation || data;
        const files = conv.files || [];

        listContainer.innerHTML = '';
        if (files.length === 0) {
            listContainer.innerHTML = '<li class="active-file-item">No files attached to this session.</li>';
            return;
        }

        files.forEach(file => {
            const fileName = typeof file === 'string' ? file : (file.name || file.filename || 'Document');
            const fileSize = file.size ? formatFileSize(file.size) : '';
            const iconClass = getFileIcon(fileName);

            const li = document.createElement('li');
            li.className = 'active-file-item';
            li.innerHTML = `
                <div class="active-file-left">
                    <i class="${iconClass} active-file-icon"></i>
                    <span class="active-file-name" title="${escapeHtml(fileName)}">${escapeHtml(fileName)}</span>
                </div>
                <span class="badge">${fileSize || 'Indexed'}</span>
            `;
            listContainer.appendChild(li);
        });
    } catch (err) {
        listContainer.innerHTML = '<li class="active-file-item text-danger">Failed to load files.</li>';
    }
}

function hideAttachedFilesModal() {
    const modal = document.getElementById('filesModal');
    if (modal) modal.classList.add('hidden');
}

async function showGeneratedFilesModal() {
    if (!AppState.currentConversationId) {
        showToast('Please open a study session first', 'warning');
        return;
    }

    const modal = document.getElementById('generatedFilesModal');
    const listContainer = document.getElementById('generatedFilesList');
    const emptyMsg = document.getElementById('noGeneratedFilesMsg');
    if (!modal || !listContainer) return;

    listContainer.innerHTML = '';
    if (emptyMsg) emptyMsg.classList.add('hidden');
    modal.classList.remove('hidden');

    try {
        const response = await fetch(`/api/conversations/${AppState.currentConversationId}/generated-files`);
        if (!response.ok) {
            throw new Error('Failed to load generated files');
        }

        const data = await response.json();
        const files = Array.isArray(data) ? data : (data.files || []);

        if (files.length === 0) {
            if (emptyMsg) emptyMsg.classList.remove('hidden');
            return;
        }

        files.forEach(f => {
            const name = f.filename || f.name || 'Generated_Document.pdf';
            const path = f.path || '';
            const dateStr = formatDate(f.created_at);

            const li = document.createElement('li');
            li.className = 'active-file-item';
            li.innerHTML = `
                <div class="active-file-left">
                    <i class="fa-solid fa-file-pdf active-file-icon"></i>
                    <div>
                        <div class="active-file-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
                        <small style="color: var(--text-muted); font-size: 0.72rem;">${escapeHtml(path)}</small>
                    </div>
                </div>
                <span class="badge">${dateStr}</span>
            `;
            listContainer.appendChild(li);
        });
    } catch (err) {
        console.error('Error fetching generated files:', err);
        if (emptyMsg) emptyMsg.classList.remove('hidden');
    }
}

function hideGeneratedFilesModal() {
    const modal = document.getElementById('generatedFilesModal');
    if (modal) modal.classList.add('hidden');
}

// ============================================================================
// Editable Title Handlers
// ============================================================================

function enableTitleEditing() {
    if (!AppState.currentConversationId) return;

    const titleEl = document.getElementById('activeConversationTitle');
    const inputEl = document.getElementById('titleEditInput');
    const renameBtn = document.getElementById('renameTitleBtn');

    if (!titleEl || !inputEl) return;

    inputEl.value = titleEl.textContent.trim();
    titleEl.classList.add('hidden');
    if (renameBtn) renameBtn.classList.add('hidden');

    inputEl.classList.remove('hidden');
    inputEl.focus();
    inputEl.select();
}

function cancelTitleEditing() {
    const titleEl = document.getElementById('activeConversationTitle');
    const inputEl = document.getElementById('titleEditInput');
    const renameBtn = document.getElementById('renameTitleBtn');

    if (inputEl) inputEl.classList.add('hidden');
    if (titleEl) titleEl.classList.remove('hidden');
    if (renameBtn) renameBtn.classList.remove('hidden');
}

async function saveConversationTitle() {
    const inputEl = document.getElementById('titleEditInput');
    if (!inputEl || inputEl.classList.contains('hidden')) return;

    const newTitle = inputEl.value.trim();
    cancelTitleEditing();

    if (!newTitle || !AppState.currentConversationId) return;

    const titleEl = document.getElementById('activeConversationTitle');
    if (titleEl && titleEl.textContent.trim() === newTitle) return;

    try {
        const response = await fetch(`/api/conversations/${AppState.currentConversationId}/title`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        });

        if (!response.ok) {
            throw new Error('Failed to update title');
        }

        updateTopBarTitle(newTitle);

        // Update local state and sidebar item
        const conv = AppState.conversations.find(c => c.id === AppState.currentConversationId);
        if (conv) conv.title = newTitle;
        renderConversationList(AppState.conversations);

        showToast('Title updated', 'info');
    } catch (err) {
        console.error('Error saving title:', err);
        showToast(err.message, 'error');
    }
}

function updateTopBarTitle(title) {
    const titleEl = document.getElementById('activeConversationTitle');
    if (titleEl) titleEl.textContent = title;
}

function updateAttachedFilesBadge(files) {
    const group = document.getElementById('activeFilesBadgeGroup');
    const countEl = document.getElementById('attachedFilesCount');
    if (!group || !countEl) return;

    const count = files ? files.length : 0;
    countEl.textContent = `${count} ${count === 1 ? 'File' : 'Files'}`;
    group.classList.remove('hidden');
}

// ============================================================================
// UI Screen Switchers & Sidebar Control
// ============================================================================

function showWelcomeScreen() {
    hideAllScreens();
    const screen = document.getElementById('welcomeScreen');
    if (screen) screen.classList.remove('hidden');
    updateTopBarTitle('Study Buddy');
    const filesGroup = document.getElementById('activeFilesBadgeGroup');
    if (filesGroup) filesGroup.classList.add('hidden');
}

function showUploadScreen() {
    hideAllScreens();
    const screen = document.getElementById('uploadScreen');
    if (screen) screen.classList.remove('hidden');
    updateTopBarTitle('New Study Session');
    const filesGroup = document.getElementById('activeFilesBadgeGroup');
    if (filesGroup) filesGroup.classList.add('hidden');
}

function showChatScreen() {
    hideAllScreens();
    const screen = document.getElementById('chatScreen');
    if (screen) screen.classList.remove('hidden');
    const textarea = document.getElementById('chatTextarea');
    if (textarea) textarea.focus();
}

function hideAllScreens() {
    document.querySelectorAll('.view-screen').forEach(s => s.classList.add('hidden'));
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('active');
}

// ============================================================================
// Toast Notifications & Utilities
// ============================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let iconClass = 'fa-solid fa-circle-info';
    if (type === 'success') iconClass = 'fa-solid fa-circle-check';
    if (type === 'error') iconClass = 'fa-solid fa-triangle-exclamation';
    if (type === 'warning') iconClass = 'fa-solid fa-circle-exclamation';

    toast.innerHTML = `
        <i class="${iconClass} toast-icon"></i>
        <div class="toast-message">${escapeHtml(message)}</div>
        <button class="toast-close-btn" title="Dismiss">
            <i class="fa-solid fa-xmark"></i>
        </button>
    `;

    toast.querySelector('.toast-close-btn').addEventListener('click', () => {
        dismissToast(toast);
    });

    container.appendChild(toast);

    // Auto dismiss after 4.5 seconds
    setTimeout(() => {
        dismissToast(toast);
    }, 4500);
}

function dismissToast(toast) {
    if (!toast || !toast.parentNode) return;
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 250);
}

function renderMarkdown(text) {
    if (!text) return '';
    if (window.marked && typeof window.marked.parse === 'function') {
        try {
            return window.marked.parse(text);
        } catch (e) {
            console.error('Markdown parse error:', e);
            return escapeHtml(text).replace(/\n/g, '<br>');
        }
    }
    return escapeHtml(text).replace(/\n/g, '<br>');
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatDate(dateInput, includeTime = false) {
    if (!dateInput) return 'Recently';
    try {
        const d = new Date(dateInput);
        if (isNaN(d.getTime())) return 'Recently';

        const now = new Date();
        const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));

        if (diffDays === 0) {
            if (includeTime) {
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            }
            return 'Today';
        } else if (diffDays === 1) {
            return 'Yesterday';
        } else if (diffDays < 7) {
            return `${diffDays}d ago`;
        } else {
            return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
        }
    } catch {
        return 'Recently';
    }
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    switch (ext) {
        case 'pdf': return 'fa-solid fa-file-pdf';
        case 'doc':
        case 'docx': return 'fa-solid fa-file-word';
        case 'txt':
        case 'md': return 'fa-solid fa-file-lines';
        case 'ppt':
        case 'pptx': return 'fa-solid fa-file-powerpoint';
        default: return 'fa-regular fa-file';
    }
}
