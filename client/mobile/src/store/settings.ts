/**
 * Settings store — persists API URL via AsyncStorage.
 */
import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";

const STORAGE_KEY = "ai_scribe_settings";
const DEFAULT_API_URL = "http://localhost:8000";

interface SettingsState {
  apiUrl: string;
  loaded: boolean;
  setApiUrl: (url: string) => void;
  load: () => Promise<void>;
}

export const useSettings = create<SettingsState>((set, get) => ({
  apiUrl: DEFAULT_API_URL,
  loaded: false,
  setApiUrl: (url: string) => {
    set({ apiUrl: url });
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ apiUrl: url }));
  },
  load: async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed.apiUrl) set({ apiUrl: parsed.apiUrl });
      }
    } catch {
      // ignore
    }
    set({ loaded: true });
  },
}));

/** Synchronous getter for API URL (used by api.ts outside of React) */
export function getApiUrl(): string {
  return useSettings.getState().apiUrl;
}
