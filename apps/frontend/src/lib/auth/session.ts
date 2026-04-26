let _sessionActive = false;

function _canUseStorage(): boolean {
  return typeof sessionStorage !== "undefined";
}

export function loadSession() {
  return {
    hasSession: _sessionActive || (_canUseStorage() && sessionStorage.getItem("_sa") === "1"),
  };
}

export function saveSession() {
  _sessionActive = true;
  if (_canUseStorage()) sessionStorage.setItem("_sa", "1");
}

export function clearSession() {
  _sessionActive = false;
  if (_canUseStorage()) sessionStorage.removeItem("_sa");
}
