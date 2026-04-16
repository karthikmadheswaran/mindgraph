import { createClient } from "@supabase/supabase-js";
import { getRuntimeConfig } from "./runtimeConfig";

const supabaseUrl = getRuntimeConfig("REACT_APP_SUPABASE_URL");
const supabaseAnonKey = getRuntimeConfig("REACT_APP_SUPABASE_ANON_KEY");

const authNotConfiguredError = {
  message: "Authentication is not configured for this deployment.",
};

const missingSupabaseClient = {
  auth: {
    getSession: async () => ({ data: { session: null }, error: null }),
    onAuthStateChange: () => ({
      data: {
        subscription: {
          unsubscribe: () => {},
        },
      },
    }),
    signOut: async () => ({ error: null }),
    signInWithPassword: async () => ({
      data: { session: null },
      error: authNotConfiguredError,
    }),
    signUp: async () => ({
      data: { session: null },
      error: authNotConfiguredError,
    }),
  },
};

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey)
  : missingSupabaseClient;
