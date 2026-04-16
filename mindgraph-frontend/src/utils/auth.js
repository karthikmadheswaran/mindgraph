import { supabase } from "../supabaseClient";
import { getRuntimeConfig } from "../runtimeConfig";

export const API =
  getRuntimeConfig("REACT_APP_API_URL") ||
  "https://mindgraph-production.up.railway.app";

export async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) return {};

  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}
