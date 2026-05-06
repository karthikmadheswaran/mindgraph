import * as Sentry from "@sentry/react";
import { getRuntimeConfig } from "./runtimeConfig";

export function initSentry() {
  const dsn = getRuntimeConfig("REACT_APP_SENTRY_DSN");
  if (!dsn) return;
  Sentry.init({
    dsn,
    integrations: [Sentry.browserTracingIntegration()],
    environment: "production",
    tracesSampleRate: 1.0,
    replaysSessionSampleRate: 0,
    beforeSend(event) {
      // Strip request body and cookies — journal content is private
      if (event.request) {
        delete event.request.data;
        delete event.request.cookies;
      }
      return event;
    },
  });
}
