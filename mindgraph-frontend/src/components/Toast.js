import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import "../styles/toast.css";

function ToastIcon({ type }) {
  if (type === "error") {
    return (
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  }

  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export default function Toast({
  message,
  type = "success",
  actionLabel,
  actionAriaLabel,
  onAction,
  duration = 4000,
  visible,
  onDismiss,
}) {
  useEffect(() => {
    if (!visible || duration == null) return;

    const timer = setTimeout(() => onDismiss(), duration);
    return () => clearTimeout(timer);
  }, [visible, message, type, onDismiss, duration]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className={`toast ${type}`}
          initial={{ opacity: 0, y: 40, scale: 0.95, x: "-50%" }}
          animate={{ opacity: 1, y: 0, scale: 1, x: "-50%" }}
          exit={{ opacity: 0, y: 20, scale: 0.95, x: "-50%" }}
          transition={{ type: "spring", stiffness: 400, damping: 28 }}
        >
          <span className="toast-icon">
            <ToastIcon type={type} />
          </span>
          <span className="toast-message">{message}</span>
          {actionLabel && typeof onAction === "function" && (
            <button
              type="button"
              className="toast-action"
              aria-label={actionAriaLabel || actionLabel}
              onClick={() => {
                onAction();
                onDismiss();
              }}
            >
              {actionLabel}
            </button>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
