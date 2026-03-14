/**
 * Encounters list — shows all samples with provider filter and status badges.
 */
import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  useWindowDimensions,
  TextInput,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";

import Badge from "../components/Badge";
import { colors, fontSize, spacing, radius } from "../lib/theme";
import { fetchSamples, fetchProviders, type SampleSummary, type ProviderSummary } from "../lib/api";

export default function EncountersScreen() {
  const nav = useNavigation<any>();
  const { width } = useWindowDimensions();
  const isTablet = width >= 768;
  const numColumns = isTablet ? 2 : 1;

  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [filterProvider, setFilterProvider] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async () => {
    const [s, p] = await Promise.all([fetchSamples(), fetchProviders()]);
    setSamples(s);
    setProviders(p);
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData().catch(() => {});
    setRefreshing(false);
  };

  // Filters
  const filtered = samples.filter((s) => {
    if (filterProvider && s.physician !== filterProvider) return false;
    if (filterMode && s.mode !== filterMode) return false;
    if (search && !s.sample_id.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const scoreVariant = (score: number | null | undefined) => {
    if (score == null) return "neutral" as const;
    if (score >= 4.5) return "success" as const;
    if (score >= 4.0) return "info" as const;
    if (score >= 3.5) return "warning" as const;
    return "error" as const;
  };

  const renderItem = ({ item }: { item: SampleSummary }) => {
    const score = item.quality?.overall;
    return (
      <TouchableOpacity
        style={[styles.card, isTablet && styles.tabletCard]}
        onPress={() => nav.navigate("EncounterDetail", { sampleId: item.sample_id })}
        activeOpacity={0.7}
      >
        <View style={styles.cardHeader}>
          <View style={{ flex: 1 }}>
            <Text style={styles.sampleId} numberOfLines={1}>{item.sample_id}</Text>
            <Text style={styles.physician}>{item.physician}</Text>
          </View>
          {score != null && (
            <Badge label={score.toFixed(2)} variant={scoreVariant(score)} />
          )}
        </View>

        <View style={styles.cardFooter}>
          <Badge label={item.mode} variant={item.mode === "dictation" ? "info" : "success"} />
          {item.latest_version && (
            <Text style={styles.versionText}>{item.latest_version}</Text>
          )}
          {item.has_gold && (
            <Ionicons name="star" size={12} color="#F59E0B" style={{ marginLeft: spacing.xs }} />
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* Search */}
      <View style={[styles.searchRow, isTablet && styles.tabletSearchRow]}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color={colors.textTertiary} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search encounters..."
            style={styles.searchInput}
            placeholderTextColor={colors.textTertiary}
          />
        </View>
      </View>

      {/* Filter chips */}
      <View style={styles.filterRow}>
        <TouchableOpacity
          style={[styles.chip, filterMode === null && styles.chipActive]}
          onPress={() => setFilterMode(null)}
        >
          <Text style={[styles.chipText, filterMode === null && styles.chipTextActive]}>All</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.chip, filterMode === "dictation" && styles.chipActive]}
          onPress={() => setFilterMode(filterMode === "dictation" ? null : "dictation")}
        >
          <Text style={[styles.chipText, filterMode === "dictation" && styles.chipTextActive]}>Dictation</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.chip, filterMode === "ambient" && styles.chipActive]}
          onPress={() => setFilterMode(filterMode === "ambient" ? null : "ambient")}
        >
          <Text style={[styles.chipText, filterMode === "ambient" && styles.chipTextActive]}>Ambient</Text>
        </TouchableOpacity>

        {/* Provider filter */}
        {providers.length > 0 && (
          <>
            <View style={styles.divider} />
            {providers.slice(0, isTablet ? 6 : 3).map((p) => (
              <TouchableOpacity
                key={p.id}
                style={[styles.chip, filterProvider === p.id && styles.chipActive]}
                onPress={() => setFilterProvider(filterProvider === p.id ? null : p.id)}
              >
                <Text style={[styles.chipText, filterProvider === p.id && styles.chipTextActive]} numberOfLines={1}>
                  {p.name?.split(" ").pop() ?? p.id}
                </Text>
              </TouchableOpacity>
            ))}
          </>
        )}
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(s) => s.sample_id}
        renderItem={renderItem}
        numColumns={numColumns}
        key={numColumns} // Force re-render on column change
        contentContainerStyle={[styles.listContent, isTablet && styles.tabletListContent]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="document-text-outline" size={40} color={colors.textTertiary} />
            <Text style={styles.emptyText}>No encounters found</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  searchRow: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  tabletSearchRow: { maxWidth: 900, alignSelf: "center", width: "100%" },
  searchBox: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
  },
  searchInput: { flex: 1, paddingVertical: spacing.sm, marginLeft: spacing.sm, fontSize: fontSize.sm, color: colors.text },
  filterRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  chipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  chipText: { fontSize: fontSize.xs, color: colors.textSecondary, fontWeight: "500" },
  chipTextActive: { color: colors.textInverse },
  divider: { width: 1, height: 20, backgroundColor: colors.border, alignSelf: "center" },
  listContent: { padding: spacing.lg, gap: spacing.md },
  tabletListContent: { maxWidth: 900, alignSelf: "center", width: "100%" },
  card: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabletCard: { marginHorizontal: spacing.xs },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  sampleId: { fontSize: fontSize.sm, fontWeight: "600", color: colors.text },
  physician: { fontSize: fontSize.xs, color: colors.textSecondary, marginTop: 2 },
  cardFooter: { flexDirection: "row", alignItems: "center", marginTop: spacing.md, gap: spacing.sm },
  versionText: { fontSize: fontSize.xs, color: colors.textTertiary, fontWeight: "500" },
  empty: { alignItems: "center", marginTop: 80 },
  emptyText: { fontSize: fontSize.sm, color: colors.textTertiary, marginTop: spacing.md },
});
