import React from 'react';
import ReactDOM from 'react-dom/client';
import * as Sentry from '@sentry/react';
import './index.css';
import App from './App';
import { initSentry } from './sentry';
import { initPostHog } from './posthog';
import reportWebVitals from './reportWebVitals';

initSentry();
initPostHog();

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={<p>Something went wrong.</p>}>
      <App />
    </Sentry.ErrorBoundary>
  </React.StrictMode>
);

reportWebVitals();
