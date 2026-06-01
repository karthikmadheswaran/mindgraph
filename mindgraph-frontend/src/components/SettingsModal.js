import { useEffect, useState } from "react";
import { API, authHeaders } from "../utils/auth";
import "../styles/settings-modal.css";

const COMMON_TIMEZONES = [
  "Pacific/Honolulu",
  "America/Anchorage",
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Moscow",
  "Africa/Cairo",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Bangkok",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Pacific/Auckland",
];

function getAllTimezones() {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return COMMON_TIMEZONES;
  }
}

export default function SettingsModal({ isOpen, onClose }) {
  const [timezone, setTimezone] = useState("");
  const [allTimezones, setAllTimezones] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setAllTimezones(getAllTimezones());
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setSaved(false);
    setLoading(true);
    authHeaders().then((headers) =>
      fetch(`${API}/users/me/timezone`, { headers })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((data) => {
          setTimezone(data.timezone || "UTC");
          setLoading(false);
        })
        .catch(() => {
          setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
          setLoading(false);
        })
    );
  }, [isOpen]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/users/me/timezone`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ timezone }),
      });
      if (!res.ok) throw new Error("save failed");
      setSaved(true);
    } catch {
      // silent
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button type="button" className="settings-close" onClick={onClose}>
            &times;
          </button>
        </div>
        <div className="settings-body">
          <label className="settings-label" htmlFor="tz-select">
            Timezone
          </label>
          <p className="settings-hint">
            Used for time-of-day queries in Ask (e.g. "what did I write this morning").
          </p>
          {loading ? (
            <span className="settings-loading">Loading...</span>
          ) : (
            <select
              id="tz-select"
              className="settings-select"
              value={timezone}
              onChange={(e) => {
                setTimezone(e.target.value);
                setSaved(false);
              }}
            >
              {allTimezones.map((tz) => (
                <option key={tz} value={tz}>
                  {tz.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="settings-save"
            onClick={handleSave}
            disabled={saving || loading}
          >
            {saving ? "Saving..." : saved ? "Saved" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
