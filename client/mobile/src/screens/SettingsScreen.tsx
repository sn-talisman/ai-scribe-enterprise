/**
 * Settings screen — API URL configuration + offline queue management.
 */
import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  useWindowDimensions,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import Card from "../components/Card";
import Badge from "../components/Badge";
import { colors, fontSize, spacing, radius } from "../lib/theme";
import { useSettings } from "../store/settings";
import { useOfflineStore } from "../store/offline";

export default function SettingsScreen() {
  const { width } = useWindowDimensions();
  const isTablet = width >= 768;
  const { apiUrl, setApiUrl } = useSettings();
  const { queue, remove, processQueue, isOnline, checkConnectivity } = useOfflineStore();
  const [urlDraft, setUrlDraft] = useState(apiUrl);

  const saveUrl = () => {
    const trimmed = urlDraft.trim().replace(/\/+$/, "");
    if (!trimmed) {
      Alert.alert("Invalid URL", "API URL cannot be empty.");
      return;
    }
    setApiUrl(trimmed);
    Alert.alert("Saved", `API URL set to: ${trimmed}`);
  };

  const retryQueue = async () => {
    await checkConnectivity();
    await processQueue();
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, isTablet && styles.tabletContent]}
    >
      <Text style={styles.title}>Settings</Text>

      {/* API URL */}
      <Card>
        <Text style={styles.label}>API Server URL</Text>
        <Text style={styles.hint}>
          The FastAPI backend address. Must be reachable from this device.
        </Text>
        <TextInput
          value={urlDraft}
          onChangeText={setUrlDraft}
          style={styles.input}
          placeholder="http://192.168.1.100:8000"
          placeholderTextColor={colors.textTertiary}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <TouchableOpacity style={styles.saveBtn} onPress={saveUrl}>
          <Text style={styles.saveBtnText}>Save</Text>
        </TouchableOpacity>
      </Card>

      {/* Connection status */}
      <Card>
        <View style={styles.row}>
          <Ionicons
            name={isOnline ? "cloud-done" : "cloud-offline"}
            size={20}
            color={isOnline ? colors.brand : colors.warning}
          />
          <Text style={[styles.statusText, { color: isOnline ? colors.brand : colors.warning }]}>
            {isOnline ? "Connected" : "Offline"}
          </Text>
          <TouchableOpacity onPress={checkConnectivity} style={{ marginLeft: "auto" }}>
            <Ionicons name="refresh" size={18} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>
      </Card>

      {/* Offline queue */}
      <Card>
        <View style={styles.row}>
          <Text style={styles.label}>Offline Queue</Text>
          <Badge label={`${queue.length}`} variant={queue.length > 0 ? "warning" : "neutral"} />
        </View>

        {queue.length === 0 ? (
          <Text style={styles.hint}>No queued recordings.</Text>
        ) : (
          <>
            {queue.map((item) => (
              <View key={item.id} style={styles.queueItem}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.queueTitle}>{item.provider_id}</Text>
                  <Text style={styles.queueMeta}>
                    {item.mode} · {item.visit_type} · {new Date(item.createdAt).toLocaleString()}
                  </Text>
                  {item.error && <Text style={styles.queueError}>{item.error}</Text>}
                </View>
                <Badge
                  label={item.status}
                  variant={item.status === "failed" ? "error" : item.status === "uploading" ? "info" : "neutral"}
                />
                <TouchableOpacity onPress={() => remove(item.id)} style={{ marginLeft: spacing.sm }}>
                  <Ionicons name="trash-outline" size={18} color={colors.error} />
                </TouchableOpacity>
              </View>
            ))}
            <TouchableOpacity style={styles.retryBtn} onPress={retryQueue}>
              <Ionicons name="cloud-upload" size={16} color={colors.textInverse} />
              <Text style={styles.retryBtnText}>Retry All</Text>
            </TouchableOpacity>
          </>
        )}
      </Card>

      {/* About */}
      <Card>
        <Text style={styles.label}>About</Text>
        <Text style={styles.hint}>AI Scribe v1.0.0</Text>
        <Text style={styles.hint}>Talisman Solutions</Text>
        <Text style={[styles.hint, { marginTop: spacing.sm }]}>
          HIPAA-compliant medical documentation. All audio is processed on your own servers — zero PHI egress.
        </Text>
      </Card>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  tabletContent: { maxWidth: 640, alignSelf: "center", width: "100%" },
  title: { fontSize: fontSize.xxl, fontWeight: "700", color: colors.text },
  label: { fontSize: fontSize.sm, fontWeight: "600", color: colors.text },
  hint: { fontSize: fontSize.xs, color: colors.textSecondary, marginTop: spacing.xs },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: fontSize.sm,
    color: colors.text,
    marginTop: spacing.md,
  },
  saveBtn: {
    backgroundColor: colors.brand,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    alignSelf: "flex-start",
    marginTop: spacing.md,
  },
  saveBtnText: { color: colors.textInverse, fontWeight: "600", fontSize: fontSize.sm },
  statusText: { fontSize: fontSize.sm, fontWeight: "600", marginLeft: spacing.sm },
  queueItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  queueTitle: { fontSize: fontSize.sm, fontWeight: "600", color: colors.text },
  queueMeta: { fontSize: fontSize.xs, color: colors.textSecondary },
  queueError: { fontSize: fontSize.xs, color: colors.error, marginTop: 2 },
  retryBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  retryBtnText: { color: colors.textInverse, fontWeight: "600", fontSize: fontSize.sm },
});
