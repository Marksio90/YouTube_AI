let hasClientSession = false;

export function loadSession() {
  return { hasSession: hasClientSession };
}

export function saveSession() {
  hasClientSession = true;
}

export function clearSession() {
  hasClientSession = false;
}
