// Shared fetch helpers reused by every feature page. Keeps error handling
// and JSON parsing consistent so feature-specific JS only deals with data.

async function handleJsonResponse(response) {
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
