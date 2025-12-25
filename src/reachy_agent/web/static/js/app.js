/**
 * Reachy Agent Dashboard Application
 *
 * Handles WebSocket communication, chat interface, video streaming,
 * and permission confirmation modals.
 */

class ReachyDashboard {
    constructor() {
        // Configuration
        this.wsUrl = `ws://${window.location.host}/ws`;
        this.apiUrl = '/api';
        this.daemonUrl = null;  // Set from status endpoint
        this.videoFrameInterval = 100;  // ms between frames (~10 FPS)

        // State
        this.ws = null;
        this.wsReconnectDelay = 1000;
        this.videoRunning = false;
        this.videoIntervalId = null;
        this.lastFrameTime = 0;
        this.frameCount = 0;
        this.pendingConfirmation = null;
        this.confirmationTimer = null;

        // DOM elements
        this.elements = {
            agentStatus: document.getElementById('agent-status'),
            robotStatus: document.getElementById('robot-status'),
            wsStatus: document.getElementById('ws-status'),
            chatMessages: document.getElementById('chat-messages'),
            chatForm: document.getElementById('chat-form'),
            chatInput: document.getElementById('chat-input'),
            clearHistoryBtn: document.getElementById('clear-history-btn'),
            robotCamera: document.getElementById('robot-camera'),
            videoPlaceholder: document.getElementById('video-placeholder'),
            videoToggle: document.getElementById('video-toggle'),
            videoFps: document.getElementById('video-fps'),
            connectionType: document.getElementById('connection-type'),
            headPosition: document.getElementById('head-position'),
            turnCount: document.getElementById('turn-count'),
            notifications: document.getElementById('notifications'),
            confirmationModal: document.getElementById('confirmation-modal'),
            modalTitle: document.getElementById('modal-title'),
            modalTimer: document.getElementById('modal-timer'),
            modalToolName: document.getElementById('modal-tool-name'),
            modalReason: document.getElementById('modal-reason'),
            modalParams: document.getElementById('modal-params'),
            modalApprove: document.getElementById('modal-approve'),
            modalDeny: document.getElementById('modal-deny'),
            toastContainer: document.getElementById('toast-container'),
        };

        this.init();
    }

    init() {
        // Connect WebSocket
        this.connectWebSocket();

        // Set up event listeners
        this.setupEventListeners();

        // Fetch initial status
        this.fetchStatus();
    }

    // WebSocket Management
    connectWebSocket() {
        this.updateWsStatus('connecting');

        this.ws = new WebSocket(this.wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateWsStatus('connected');
            this.wsReconnectDelay = 1000;  // Reset delay
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateWsStatus('disconnected');
            // Reconnect with exponential backoff
            setTimeout(() => this.connectWebSocket(), this.wsReconnectDelay);
            this.wsReconnectDelay = Math.min(this.wsReconnectDelay * 2, 30000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onmessage = (event) => {
            this.handleWebSocketMessage(JSON.parse(event.data));
        };
    }

    handleWebSocketMessage(message) {
        console.log('WS message:', message.type, message);

        switch (message.type) {
            case 'status_update':
                this.handleStatusUpdate(message.status);
                break;

            case 'history':
                this.loadHistory(message.messages);
                break;

            case 'agent_response':
                this.addMessage('assistant', message.text);
                this.elements.turnCount.textContent = message.turn_number;
                break;

            case 'confirmation_request':
                this.showConfirmation(message);
                break;

            case 'confirmation_timeout':
                this.hideConfirmation();
                this.showToast(`Confirmation timed out for ${message.tool_name}`, 'warning');
                break;

            case 'notification':
                this.addNotification(message);
                break;

            case 'error':
                this.showToast(`Error in ${message.tool_name}: ${message.error}`, 'error');
                break;

            case 'tool_start':
                this.addNotification({
                    tool_name: message.tool_name,
                    message: 'Executing...',
                    tier: 1,
                });
                break;

            case 'tool_complete':
                this.addNotification({
                    tool_name: message.tool_name,
                    message: `Completed in ${message.duration_ms}ms`,
                    tier: 1,
                });
                break;

            case 'pong':
                // Heartbeat response
                break;

            default:
                console.log('Unknown message type:', message.type);
        }
    }

    updateWsStatus(status) {
        const el = this.elements.wsStatus;
        el.className = 'badge';

        switch (status) {
            case 'connected':
                el.textContent = 'WebSocket: Connected';
                el.classList.add('badge-connected');
                break;
            case 'connecting':
                el.textContent = 'WebSocket: Connecting';
                el.classList.add('badge-connecting');
                break;
            default:
                el.textContent = 'WebSocket: Disconnected';
                el.classList.add('badge-disconnected');
        }
    }

    // Event Listeners
    setupEventListeners() {
        // Chat form
        this.elements.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Clear history
        this.elements.clearHistoryBtn.addEventListener('click', () => {
            this.clearHistory();
        });

        // Video toggle
        this.elements.videoToggle.addEventListener('click', () => {
            this.toggleVideo();
        });

        // Confirmation modal
        this.elements.modalApprove.addEventListener('click', () => {
            this.respondToConfirmation(true);
        });

        this.elements.modalDeny.addEventListener('click', () => {
            this.respondToConfirmation(false);
        });

        // Keyboard shortcut for confirmation
        document.addEventListener('keydown', (e) => {
            if (this.pendingConfirmation) {
                if (e.key === 'Enter') {
                    this.respondToConfirmation(true);
                } else if (e.key === 'Escape') {
                    this.respondToConfirmation(false);
                }
            }
        });
    }

    // API Methods
    async fetchStatus() {
        try {
            const response = await fetch(`${this.apiUrl}/status`);
            const status = await response.json();

            this.daemonUrl = status.daemon_url;
            this.handleStatusUpdate({
                agent_connected: status.agent_connected,
                robot_connected: status.robot_connected,
                turn_count: status.turn_count,
                robot_status: status.robot_status,
            });
        } catch (error) {
            console.error('Failed to fetch status:', error);
        }
    }

    handleStatusUpdate(status) {
        // Agent status
        if (status.agent_connected) {
            this.elements.agentStatus.textContent = 'Agent: Connected';
            this.elements.agentStatus.className = 'badge badge-connected';
        } else {
            this.elements.agentStatus.textContent = 'Agent: Demo Mode';
            this.elements.agentStatus.className = 'badge badge-connecting';
        }

        // Robot status
        if (status.robot_connected) {
            this.elements.robotStatus.textContent = 'Robot: Connected';
            this.elements.robotStatus.className = 'badge badge-connected';
        } else {
            this.elements.robotStatus.textContent = 'Robot: Disconnected';
            this.elements.robotStatus.className = 'badge badge-disconnected';
        }

        // Turn count
        if (status.turn_count !== undefined) {
            this.elements.turnCount.textContent = status.turn_count;
        }

        // Robot details
        if (status.robot_status) {
            const rs = status.robot_status;
            this.elements.connectionType.textContent = rs.connection_type || 'Simulator';

            if (rs.head) {
                const h = rs.head;
                this.elements.headPosition.textContent =
                    `R:${h.roll?.toFixed(1) || 0} P:${h.pitch?.toFixed(1) || 0} Y:${h.yaw?.toFixed(1) || 0}`;
            }
        }
    }

    // Chat Methods
    async sendMessage() {
        const message = this.elements.chatInput.value.trim();
        if (!message) return;

        // Add user message immediately
        this.addMessage('user', message);
        this.elements.chatInput.value = '';

        // Send to server
        try {
            const response = await fetch(`${this.apiUrl}/prompt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message }),
            });

            const result = await response.json();
            // Response comes via WebSocket, but fallback here
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                this.addMessage('assistant', result.response);
                this.elements.turnCount.textContent = result.turn_number;
            }
        } catch (error) {
            console.error('Failed to send message:', error);
            this.showToast('Failed to send message', 'error');
        }
    }

    /**
     * Sanitize HTML content to prevent XSS attacks.
     * Uses DOMPurify if available, otherwise falls back to text-only.
     */
    sanitizeHtml(html) {
        if (typeof DOMPurify !== 'undefined') {
            return DOMPurify.sanitize(html, {
                ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'h1', 'h2', 'h3', 'ul', 'ol', 'li', 'a', 'blockquote'],
                ALLOWED_ATTR: ['href', 'target', 'rel'],
            });
        }
        // Fallback: create element and extract text to avoid XSS
        const temp = document.createElement('div');
        temp.textContent = html;
        return temp.textContent;
    }

    /**
     * Render markdown content safely using marked + DOMPurify.
     */
    renderMarkdown(content) {
        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            const rawHtml = marked.parse(content);
            return this.sanitizeHtml(rawHtml);
        }
        // Fallback to plain text
        return this.escapeHtml(content);
    }

    /**
     * Escape HTML special characters.
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.textContent;
    }

    addMessage(role, content) {
        const div = document.createElement('div');
        div.className = `message ${role}`;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Render markdown for assistant messages (with sanitization)
        if (role === 'assistant' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            const sanitized = this.renderMarkdown(content);
            contentDiv.innerHTML = DOMPurify.sanitize(sanitized);
        } else {
            contentDiv.textContent = content;
        }

        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = new Date().toLocaleTimeString();

        div.appendChild(contentDiv);
        div.appendChild(timeDiv);

        this.elements.chatMessages.appendChild(div);
        this.scrollToBottom();
    }

    loadHistory(messages) {
        // Clear existing messages except system welcome
        const systemMsg = this.elements.chatMessages.querySelector('.message.system');
        while (this.elements.chatMessages.firstChild) {
            this.elements.chatMessages.removeChild(this.elements.chatMessages.firstChild);
        }
        if (systemMsg) {
            this.elements.chatMessages.appendChild(systemMsg);
        }

        // Add history messages
        messages.forEach(msg => {
            this.addMessage(msg.role, msg.content);
        });
    }

    async clearHistory() {
        try {
            await fetch(`${this.apiUrl}/history`, { method: 'DELETE' });

            // Clear UI using DOM methods
            const systemMsg = this.elements.chatMessages.querySelector('.message.system');
            while (this.elements.chatMessages.firstChild) {
                this.elements.chatMessages.removeChild(this.elements.chatMessages.firstChild);
            }
            if (systemMsg) {
                this.elements.chatMessages.appendChild(systemMsg);
            }

            this.elements.turnCount.textContent = '0';
            this.showToast('History cleared', 'success');
        } catch (error) {
            console.error('Failed to clear history:', error);
            this.showToast('Failed to clear history', 'error');
        }
    }

    scrollToBottom() {
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    }

    // Video Streaming
    toggleVideo() {
        if (this.videoRunning) {
            this.stopVideo();
        } else {
            this.startVideo();
        }
    }

    startVideo() {
        if (!this.daemonUrl) {
            this.showToast('Daemon URL not available', 'warning');
            return;
        }

        this.videoRunning = true;
        this.elements.videoToggle.textContent = 'Stop Video';
        this.frameCount = 0;
        this.lastFrameTime = performance.now();

        const frameUrl = `${this.daemonUrl}/camera/capture`;

        // Start polling frames
        this.videoIntervalId = setInterval(() => {
            this.fetchFrame(frameUrl);
        }, this.videoFrameInterval);

        // Fetch first frame immediately
        this.fetchFrame(frameUrl);
    }

    stopVideo() {
        this.videoRunning = false;
        this.elements.videoToggle.textContent = 'Start Video';
        this.elements.videoFps.textContent = '0 FPS';

        if (this.videoIntervalId) {
            clearInterval(this.videoIntervalId);
            this.videoIntervalId = null;
        }

        this.elements.robotCamera.classList.remove('active');
        this.elements.videoPlaceholder.classList.remove('hidden');
    }

    async fetchFrame(url) {
        if (!this.videoRunning) return;

        try {
            // Add timestamp to prevent caching
            const frameUrl = `${url}?t=${Date.now()}`;
            const img = this.elements.robotCamera;

            // Use new Image to preload
            const newImg = new Image();
            newImg.onload = () => {
                img.src = newImg.src;
                img.classList.add('active');
                this.elements.videoPlaceholder.classList.add('hidden');

                // Calculate FPS
                this.frameCount++;
                const now = performance.now();
                const elapsed = now - this.lastFrameTime;
                if (elapsed >= 1000) {
                    const fps = Math.round(this.frameCount * 1000 / elapsed);
                    this.elements.videoFps.textContent = `${fps} FPS`;
                    this.frameCount = 0;
                    this.lastFrameTime = now;
                }
            };
            newImg.onerror = () => {
                // Silent fail - camera may not be available
            };
            newImg.src = frameUrl;

        } catch (error) {
            // Silent fail for video frames
        }
    }

    // Confirmation Modal
    showConfirmation(data) {
        this.pendingConfirmation = data;

        this.elements.modalToolName.textContent = data.tool_name;
        this.elements.modalReason.textContent = data.reason;

        // Format parameters safely using DOM methods
        this.elements.modalParams.textContent = '';  // Clear previous
        Object.entries(data.tool_input).forEach(([key, value]) => {
            const paramDiv = document.createElement('div');
            const keySpan = document.createElement('strong');
            keySpan.textContent = key + ': ';
            paramDiv.appendChild(keySpan);
            paramDiv.appendChild(document.createTextNode(JSON.stringify(value)));
            this.elements.modalParams.appendChild(paramDiv);
        });

        // Start countdown
        let remaining = data.timeout_seconds || 60;
        this.elements.modalTimer.textContent = `${remaining}s`;

        this.confirmationTimer = setInterval(() => {
            remaining--;
            this.elements.modalTimer.textContent = `${remaining}s`;
            if (remaining <= 0) {
                this.hideConfirmation();
            }
        }, 1000);

        // Show modal
        this.elements.confirmationModal.classList.remove('hidden');
    }

    hideConfirmation() {
        this.elements.confirmationModal.classList.add('hidden');
        this.pendingConfirmation = null;

        if (this.confirmationTimer) {
            clearInterval(this.confirmationTimer);
            this.confirmationTimer = null;
        }
    }

    respondToConfirmation(approved) {
        if (!this.pendingConfirmation) return;

        // Send response via WebSocket
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'confirmation_response',
                request_id: this.pendingConfirmation.request_id,
                approved: approved,
            }));
        }

        const action = approved ? 'approved' : 'denied';
        this.showToast(`Action ${action}`, approved ? 'success' : 'warning');

        this.hideConfirmation();
    }

    // Notifications
    addNotification(data) {
        const div = document.createElement('div');
        div.className = `notification-item tier-${data.tier || 2}`;

        const strong = document.createElement('strong');
        strong.textContent = data.tool_name + ': ';
        div.appendChild(strong);
        div.appendChild(document.createTextNode(data.message));

        this.elements.notifications.insertBefore(div, this.elements.notifications.firstChild);

        // Keep only last 10 notifications
        while (this.elements.notifications.children.length > 10) {
            this.elements.notifications.removeChild(this.elements.notifications.lastChild);
        }
    }

    // Toast Notifications
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;

        this.elements.toastContainer.appendChild(toast);

        // Remove after 5 seconds
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new ReachyDashboard();
});
