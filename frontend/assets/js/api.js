// Shared fetch helpers reused by every feature page. Keeps error handling
// and JSON parsing consistent so feature-specific JS only deals with data.

// --- Rate-limit badge -------------------------------------------------
// Every backend response carries X-RateLimit-{Limit,Remaining,Reset}
// headers (see app/main.py) - read them off responses this page was
// already making, and reflect them in a small fixed badge. No dedicated
// polling: the only extra request is a one-shot GET on page load, to have
// a number on screen before the user's first action.

let _rateLimitResetTimer = null;

// Just the exact count left, not "N/M" - the limit isn't something the user
// needs to track, only how many calls they can still make right now.
function _rateLimitBadgeText(remaining, secondsLeft) {
  const left = `${remaining} request${remaining === 1 ? "" : "s"} left`;
  return secondsLeft > 0 ? `${left} · resets in ${secondsLeft}s` : left;
}

function _renderRateLimitBadge(remaining, limit, resetSeconds, windowSeconds) {
  const badge = document.getElementById("rate-limit-badge");
  if (!badge) return;

  const known = remaining !== null && limit !== null;
  // Nothing's been spent yet (a fresh window, or right after one just
  // reset) - a countdown here would just be ticking down to reset a budget
  // that's already full, which reads as a bug rather than information.
  const nothingToReset = known && remaining >= limit;
  badge.textContent = known ? _rateLimitBadgeText(remaining, nothingToReset ? 0 : resetSeconds) : "";
  badge.title =
    known && windowSeconds
      ? `Simple demo rate limit (not Mistral's own) — up to ${limit} requests per ${windowSeconds}s`
      : "";
  badge.hidden = !known;

  if (_rateLimitResetTimer) clearInterval(_rateLimitResetTimer);
  if (!known || nothingToReset) return;

  let secondsLeft = resetSeconds;
  _rateLimitResetTimer = setInterval(() => {
    secondsLeft -= 1;
    if (secondsLeft <= 0) {
      clearInterval(_rateLimitResetTimer);
      // The backend's fixed window always resets fully once it elapses (see
      // _reset_if_elapsed in rate_limiter.py) - apply that same rule here
      // instead of leaving the last-known `remaining` stale until the next
      // real request comes back with fresh headers.
      badge.textContent = _rateLimitBadgeText(limit, 0);
      return;
    }
    badge.textContent = _rateLimitBadgeText(remaining, secondsLeft);
  }, 1000);
}

function _updateRateLimitBadgeFromResponse(response) {
  const remaining = response.headers.get("X-RateLimit-Remaining");
  const limit = response.headers.get("X-RateLimit-Limit");
  const reset = response.headers.get("X-RateLimit-Reset");
  const window = response.headers.get("X-RateLimit-Window-Seconds");
  if (remaining === null || limit === null || reset === null) return;
  _renderRateLimitBadge(Number(remaining), Number(limit), Number(reset), Number(window));
}

function _injectRateLimitBadge() {
  const badge = document.createElement("div");
  badge.id = "rate-limit-badge";
  badge.className = "rate-limit-badge";
  badge.hidden = true;
  document.body.appendChild(badge);
}

_injectRateLimitBadge();
// One-shot seed so the badge shows a real number before the user's first
// action - not a poll, this fires once per page load only.
fetch("/api/rate-limit/status")
  .then((response) => response.json())
  .then((data) =>
    _renderRateLimitBadge(data.remaining, data.limit, data.reset_in, data.window_seconds)
  )
  .catch(() => {
    /* leave the badge hidden if this one-shot call fails */
  });
// -----------------------------------------------------------------------

async function handleJsonResponse(response) {
  _updateRateLimitBadgeFromResponse(response);

  let data = null;
  try {
    data = await response.json();
  } catch {
    // no JSON body — leave data as null
  }

  if (!response.ok) {
    const message = (data && (data.detail || data.message)) || `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }

  return data;
}

async function apiGet(path) {
  const response = await fetch(path);
  return handleJsonResponse(response);
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handleJsonResponse(response);
}

// POSTs to a Server-Sent-Events endpoint (`data: <json>\n\n` lines) and
// yields each parsed JSON message as it arrives, instead of waiting for the
// whole response like apiPost does. Used by cases whose answers are slow
// enough that a caller wants to show progress as it streams in.
async function* apiPostStream(path) {
  const response = await fetch(path, { method: "POST" });
  _updateRateLimitBadgeFromResponse(response);

  if (!response.ok) {
    await handleJsonResponse(response); // throws with the parsed error detail
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (rawEvent.startsWith("data:")) {
        const jsonText = rawEvent.slice(5).trim();
        if (jsonText) yield JSON.parse(jsonText);
      }
    }
  }
}
