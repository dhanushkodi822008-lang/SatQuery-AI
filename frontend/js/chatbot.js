/**
 * SatQuery AI — Floating Chatbot Widget (Bottom Right)
 * Real-time multimodal satellite assistant powered by Groq 120B AI, OSM Real Boundaries, and Spectral Evidence.
 */
(function () {
  'use strict';

  let fcSessionId = null;
  let isOpen = false;
  let isThinking = false;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  // Lightweight markdown-to-HTML formatter for rich assistant responses
  function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Code blocks ```...```
    html = html.replace(/```([\s\S]*?)```/g, '<pre class="fc-code-block"><code>$1</code></pre>');

    // Inline code `...`
    html = html.replace(/`([^`]+)`/g, '<code class="fc-inline-code">$1</code>');

    // Headers ### Title
    html = html.replace(/^### (.*$)/gim, '<h4 class="fc-msg-h4">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 class="fc-msg-h3">$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2 class="fc-msg-h2">$1</h2>');

    // Bold **text**
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Italic *text* or _text_
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    html = html.replace(/_([^_]+)_/g, '<em>$1</em>');

    // Unordered lists - item or * item
    html = html.replace(/^\s*[-*]\s+(.*)$/gim, '<li class="fc-list-item">$1</li>');
    html = html.replace(/(<li class="fc-list-item">.*<\/li>)/gms, '<ul class="fc-list">$1</ul>');
    html = html.replace(/<\/ul>\s*<ul class="fc-list">/g, '');

    // Convert newlines to paragraphs / breaks
    html = html.replace(/\n\n+/g, '</p><p>');
    html = html.replace(/\n/g, '<br/>');

    return `<p>${html}</p>`.replace(/<p><\/p>/g, '');
  }

  function updateLocationBadge() {
    const el = $('fc-loc-indicator');
    if (!el) return;
    const st = window.SharedState?.get?.() || {};
    const locName = st.location?.place_name || st.location?.display_name || st.location?.name;
    if (locName) {
      const shortName = locName.split(',').slice(0, 2).join(',').trim();
      el.textContent = `📍 ${shortName}`;
      el.title = locName;
    } else {
      el.textContent = '📍 Global STAC & Spectral AI';
      el.title = 'Select a location or draw AOI on map';
    }
  }

  function scrollToBottom() {
    const msgBox = $('fc-messages');
    if (msgBox) {
      msgBox.scrollTop = msgBox.scrollHeight;
    }
  }

  function appendUserBubble(text) {
    const msgBox = $('fc-messages');
    if (!msgBox) return;
    const msgDiv = document.createElement('div');
    msgDiv.className = 'fc-msg fc-msg-user';
    msgDiv.innerHTML = `
      <div class="fc-msg-content">${escapeHtml(text)}</div>
    `;
    msgBox.appendChild(msgDiv);
    scrollToBottom();
  }

  function showTypingIndicator() {
    const msgBox = $('fc-messages');
    if (!msgBox) return null;
    const typingDiv = document.createElement('div');
    typingDiv.id = 'fc-typing-indicator';
    typingDiv.className = 'fc-msg fc-msg-assistant fc-typing-msg';
    typingDiv.innerHTML = `
      <div class="fc-msg-avatar">🛰️</div>
      <div class="fc-msg-content">
        <div class="fc-typing-dots">
          <span></span><span></span><span></span>
        </div>
        <span class="fc-typing-text">Analyzing satellite bands & Groq AI...</span>
      </div>
    `;
    msgBox.appendChild(typingDiv);
    scrollToBottom();
    return typingDiv;
  }

  function removeTypingIndicator() {
    const typing = $('fc-typing-indicator');
    if (typing) typing.remove();
  }

  function appendAssistantBubble(text, meta) {
    removeTypingIndicator();
    const msgBox = $('fc-messages');
    if (!msgBox) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'fc-msg fc-msg-assistant';

    let metaChipsHtml = '';
    if (meta?.confidence) {
      const confPct = Math.round(meta.confidence * 100);
      metaChipsHtml += `<span class="fc-evidence-tag">🎯 Confidence: ${confPct}%</span>`;
    }
    if (meta?.task) {
      metaChipsHtml += `<span class="fc-evidence-tag">🛰️ ${meta.task}</span>`;
    }
    if (meta?.sources?.length) {
      const srcName = typeof meta.sources[0] === 'string' ? meta.sources[0] : (meta.sources[0]?.name || 'STAC');
      metaChipsHtml += `<span class="fc-evidence-tag">📡 ${escapeHtml(srcName)}</span>`;
    }

    msgDiv.innerHTML = `
      <div class="fc-msg-avatar">🛰️</div>
      <div class="fc-msg-content">
        <div class="fc-msg-body">${formatMarkdown(text)}</div>
        ${metaChipsHtml ? `<div class="fc-msg-footer">${metaChipsHtml}</div>` : ''}
      </div>
    `;
    msgBox.appendChild(msgDiv);
    scrollToBottom();
  }

  function dispatchClientAction(action) {
    if (!action || typeof action !== 'object') return;
    console.log('[chatbot] executing action:', action);

    const type = action.type;
    const payload = action.payload || {};

    if (type === 'set_location' && payload) {
      window.SharedState?.setLocation(payload);
      if (window.AppMain?.onLocationSelected) {
        window.AppMain.onLocationSelected(payload);
      }
    } else if (type === 'set_aoi' && payload) {
      if (payload.location) {
        window.SharedState?.setLocation(payload.location);
      }
      window.SharedState?.setAoi(payload.geojson, payload.area_km2);
      if (window.AppMain?.onAoiChanged) {
        window.AppMain.onAoiChanged(payload.geojson, payload.area_km2);
      }
    } else if (type === 'clear_aoi') {
      window.SharedState?.clearArea();
      if (window.AppMain?.clearAoi) {
        window.AppMain.clearAoi();
      }
    } else if (type === 'set_basemap' && payload.basemap) {
      window.SharedState?.setBasemap(payload.basemap);
      if (window.AppMain?.switchBasemap) {
        window.AppMain.switchBasemap(payload.basemap);
      }
    } else if (type === 'select_landcover' && payload.category) {
      if (window.AppMain?.showPage) {
        window.AppMain.showPage('area-overview');
      }
      if (window.AppMain?.selectLandcoverCategory) {
        window.AppMain.selectLandcoverCategory(payload.category);
      }
    }
    updateLocationBadge();
  }

  async function sendQuery(queryText) {
    const q = (queryText || '').trim();
    if (!q || isThinking) return;

    appendUserBubble(q);
    const input = $('fc-input');
    if (input) {
      input.value = '';
      input.style.height = 'auto';
    }

    isThinking = true;
    showTypingIndicator();

    const st = window.SharedState?.get?.() || {};
    const appCtx = window.AppMain ? {
      landcover: window.AppMain.getLastLandcover?.(),
      comparison: window.AppMain.getLastCompareResult?.(),
    } : {};
    const payload = {
      message: q,
      location: st.location?.display_name || st.location?.place_name || st.location?.name || null,
      lat: st.location?.lat,
      lon: st.location?.lon,
      bbox: st.location?.bbox || null,
      aoi: st.aoi || null,
      image_id: st.imageId || null,
      session_id: fcSessionId || null,
      context: {
        ...appCtx,
        selectedScene: st.selectedScene || null,
        aoiAreaKm2: st.aoiAreaKm2 || null,
      },
    };

    try {
      let res;
      if (window.API?.chatMessage) {
        res = await window.API.chatMessage(payload);
      } else {
        const base = (window.location.origin.includes('5500') || window.location.protocol === 'file:')
          ? 'http://127.0.0.1:8000' : '';
        const fetchRes = await fetch(base + '/api/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        res = await fetchRes.json();
      }

      if (res?.session_id) fcSessionId = res.session_id;

      const answer = res?.content
        || res?.answer_text
        || res?.answer
        || res?.message
        || (res?.success === false ? (res?.error || 'Analysis could not be computed.') : 'Analysis complete.');

      appendAssistantBubble(answer, {
        confidence: res?.confidence,
        task: res?.task || res?.detected_task,
        sources: res?.sources,
      });

      // Execute structured client actions (e.g. set_location, set_aoi, set_basemap, clear_aoi)
      if (res?.action) {
        dispatchClientAction(res.action);
      }

    } catch (err) {
      appendAssistantBubble(`⚠️ SatQuery AI is temporarily unable to process your request. Please try again.`, null);
    } finally {
      isThinking = false;
      removeTypingIndicator();
    }
  }

  function toggleChatWindow(forceState) {
    const win = $('floating-chat-window');
    const fab = $('floating-chat-toggle');
    if (!win || !fab) return;

    isOpen = typeof forceState === 'boolean' ? forceState : !isOpen;

    if (isOpen) {
      win.classList.remove('hidden-chat');
      win.offsetHeight;
      win.classList.add('open');
      fab.classList.add('active');
      const openIcon = fab.querySelector('.fab-icon-open');
      const closeIcon = fab.querySelector('.fab-icon-close');
      if (openIcon) openIcon.style.display = 'none';
      if (closeIcon) closeIcon.style.display = 'block';

      updateLocationBadge();
      scrollToBottom();
      setTimeout(() => $('fc-input')?.focus(), 100);
    } else {
      win.classList.remove('open');
      fab.classList.remove('active');
      const openIcon = fab.querySelector('.fab-icon-open');
      const closeIcon = fab.querySelector('.fab-icon-close');
      if (openIcon) openIcon.style.display = 'block';
      if (closeIcon) closeIcon.style.display = 'none';
      setTimeout(() => {
        if (!isOpen) win.classList.add('hidden-chat');
      }, 300);
    }
  }

  function clearChatHistory() {
    const msgBox = $('fc-messages');
    if (!msgBox) return;
    msgBox.innerHTML = `
      <div class="fc-msg fc-msg-assistant">
        <div class="fc-msg-avatar">🛰️</div>
        <div class="fc-msg-content">
          <div class="fc-msg-body">
            <p><strong>Chat session cleared.</strong></p>
            <p>Ask anything about Earth observation, search for locations or coordinates, select real administrative boundaries, or run remote-sensing analysis.</p>
          </div>
        </div>
      </div>
    `;
    fcSessionId = null;
  }

  function initChatbot() {
    const fab = $('floating-chat-toggle');
    const closeBtn = $('fc-btn-close');
    const clearBtn = $('fc-btn-clear');
    const sendBtn = $('fc-btn-send');
    const input = $('fc-input');
    const chipsBar = $('fc-chips-bar');

    if (fab) {
      fab.addEventListener('click', () => toggleChatWindow());
    }

    if (closeBtn) {
      closeBtn.addEventListener('click', () => toggleChatWindow(false));
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', clearChatHistory);
    }

    if (sendBtn && input) {
      sendBtn.addEventListener('click', () => sendQuery(input.value));
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendQuery(input.value);
        }
      });
      input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
      });
    }

    if (chipsBar) {
      chipsBar.addEventListener('click', (e) => {
        const chip = e.target.closest('.fc-chip');
        if (chip) {
          const q = chip.getAttribute('data-query') || chip.textContent.trim();
          sendQuery(q);
        }
      });
    }

    // Subscribe to SharedState to keep location badge updated
    if (window.SharedState?.subscribe) {
      window.SharedState.subscribe(() => {
        updateLocationBadge();
      });
    }

    updateLocationBadge();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChatbot);
  } else {
    initChatbot();
  }
})();
