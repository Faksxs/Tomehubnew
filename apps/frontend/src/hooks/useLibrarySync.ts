import { useCallback, useEffect, useRef } from "react";
import { Highlight, LibraryItem, PersonalNoteFolder } from "../types";
import {
    fetchItemsForUser,
    fetchPersonalNoteFoldersForUser,
    type OracleListCursor,
} from "../services/oracleLibraryService";
import { pollRealtimeEvents } from "../services/backendApiService";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PendingContentSyncMode = "HIGHLIGHTS" | "PERSONAL_NOTE" | "ITEM";

type PendingContentSyncEntry = {
    mode: PendingContentSyncMode;
    snapshot: LibraryItem;
    timerId: number;
};

// ---------------------------------------------------------------------------
// Pure normalize helpers (no React dependency)
// ---------------------------------------------------------------------------

const normalizeMaybeText = (value: unknown): string =>
    typeof value === "string" ? value.trim() : "";

const normalizeMaybeBoolean = (value: unknown): boolean | null =>
    typeof value === "boolean" ? value : null;

const normalizeMaybeNumber = (value: unknown): number | null => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
};

const normalizeTagList = (tags: unknown): string[] =>
    Array.isArray(tags)
        ? tags.map((tag) => String(tag || "").trim()).filter(Boolean).sort()
        : [];

const normalizeStringList = (values: unknown): string[] =>
    Array.isArray(values)
        ? values.map((v) => String(v || "").trim()).filter(Boolean).sort()
        : [];

const normalizeComparableHighlights = (highlights: Highlight[] = []) =>
    highlights
        .map((highlight) => ({
            text: normalizeMaybeText(highlight.text),
            type: String(highlight.type || "highlight").trim().toLowerCase(),
            comment: normalizeMaybeText(highlight.comment),
            pageNumber: normalizeMaybeNumber(highlight.pageNumber),
            paragraphNumber: normalizeMaybeNumber(highlight.paragraphNumber),
            chapterTitle: normalizeMaybeText(highlight.chapterTitle),
            tags: normalizeTagList(highlight.tags),
        }))
        .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));

const normalizeLentInfo = (value: unknown): { borrowerName: string; lentDate: string } | null => {
    if (!value || typeof value !== "object") return null;
    const lentInfo = value as { borrowerName?: unknown; lentDate?: unknown };
    return {
        borrowerName: normalizeMaybeText(lentInfo.borrowerName),
        lentDate: normalizeMaybeText(lentInfo.lentDate),
    };
};

const normalizeComparableItem = (item: LibraryItem) => ({
    id: normalizeMaybeText(item.id),
    type: normalizeMaybeText(item.type),
    title: normalizeMaybeText(item.title),
    author: normalizeMaybeText(item.author),
    translator: normalizeMaybeText(item.translator),
    publisher: normalizeMaybeText(item.publisher),
    publicationYear: normalizeMaybeText(item.publicationYear),
    isbn: normalizeMaybeText(item.isbn),
    url: normalizeMaybeText(item.url),
    code: normalizeMaybeText(item.code),
    status: normalizeMaybeText(item.status),
    readingStatus: normalizeMaybeText(item.readingStatus),
    tags: normalizeTagList(item.tags),
    generalNotes: normalizeMaybeText(item.generalNotes),
    summaryText: normalizeMaybeText(item.summaryText),
    contentLanguageMode: normalizeMaybeText(item.contentLanguageMode),
    contentLanguageResolved: normalizeMaybeText(item.contentLanguageResolved),
    sourceLanguageHint: normalizeMaybeText(item.sourceLanguageHint),
    languageDecisionReason: normalizeMaybeText(item.languageDecisionReason),
    languageDecisionConfidence: normalizeMaybeNumber(item.languageDecisionConfidence),
    personalNoteCategory: normalizeMaybeText(item.personalNoteCategory),
    personalFolderId: normalizeMaybeText(item.personalFolderId),
    folderPath: normalizeMaybeText(item.folderPath),
    coverUrl: normalizeMaybeText(item.coverUrl),
    lentInfo: normalizeLentInfo(item.lentInfo),
    highlights: normalizeComparableHighlights(item.highlights || []),
    addedAt: normalizeMaybeNumber(item.addedAt),
    isFavorite: normalizeMaybeBoolean(item.isFavorite),
    isIngested: normalizeMaybeBoolean(item.isIngested),
    pageCount: normalizeMaybeNumber(item.pageCount),
    castTop: normalizeStringList(item.castTop),
    rating: normalizeMaybeNumber(item.rating),
});

const areItemsEquivalent = (a: LibraryItem, b: LibraryItem): boolean =>
    JSON.stringify(normalizeComparableItem(a)) === JSON.stringify(normalizeComparableItem(b));

const reconcileItemsWithPrevious = (
    previousItems: LibraryItem[],
    nextItems: LibraryItem[]
): LibraryItem[] => {
    if (previousItems.length === 0) return nextItems;

    // If the same item set arrives with the same content but different order,
    // keep previous reference to prevent needless render churn/flicker.
    if (previousItems.length === nextItems.length) {
        const nextById = new Map(nextItems.map((item) => [item.id, item]));
        let allEquivalent = true;
        for (let i = 0; i < previousItems.length; i += 1) {
            const previousItem = previousItems[i];
            const nextItem = nextById.get(previousItem.id);
            if (!nextItem || !areItemsEquivalent(previousItem, nextItem)) {
                allEquivalent = false;
                break;
            }
        }
        if (allEquivalent) {
            return previousItems;
        }
    }

    const previousById = new Map(previousItems.map((item) => [item.id, item]));
    let changed = previousItems.length !== nextItems.length;

    const reconciled = nextItems.map((nextItem) => {
        const previousItem = previousById.get(nextItem.id);
        if (!previousItem) {
            changed = true;
            return nextItem;
        }

        if (areItemsEquivalent(previousItem, nextItem)) {
            return previousItem;
        }

        changed = true;
        return nextItem;
    });

    if (!changed) {
        return previousItems;
    }

    return reconciled;
};

const areFoldersEquivalent = (a: PersonalNoteFolder, b: PersonalNoteFolder): boolean =>
    normalizeMaybeText(a.id) === normalizeMaybeText(b.id) &&
    normalizeMaybeText(a.category) === normalizeMaybeText(b.category) &&
    normalizeMaybeText(a.name) === normalizeMaybeText(b.name) &&
    normalizeMaybeNumber(a.order) === normalizeMaybeNumber(b.order) &&
    normalizeMaybeNumber(a.createdAt) === normalizeMaybeNumber(b.createdAt) &&
    normalizeMaybeNumber(a.updatedAt) === normalizeMaybeNumber(b.updatedAt);

const reconcileFoldersWithPrevious = (
    previousFolders: PersonalNoteFolder[],
    nextFolders: PersonalNoteFolder[]
): PersonalNoteFolder[] => {
    if (previousFolders.length === 0) return nextFolders;

    if (previousFolders.length === nextFolders.length) {
        const nextById = new Map(nextFolders.map((folder) => [folder.id, folder]));
        let allEquivalent = true;
        for (let i = 0; i < previousFolders.length; i += 1) {
            const previousFolder = previousFolders[i];
            const nextFolder = nextById.get(previousFolder.id);
            if (!nextFolder || !areFoldersEquivalent(previousFolder, nextFolder)) {
                allEquivalent = false;
                break;
            }
        }
        if (allEquivalent) {
            return previousFolders;
        }
    }

    if (previousFolders.length !== nextFolders.length) {
        return nextFolders;
    }

    let changed = false;
    for (let i = 0; i < nextFolders.length; i += 1) {
        if (!areFoldersEquivalent(previousFolders[i], nextFolders[i])) {
            changed = true;
            break;
        }
    }
    return changed ? nextFolders : previousFolders;
};

// ---------------------------------------------------------------------------
// isServerCaughtUpWithPending (pure function)
// ---------------------------------------------------------------------------

function isServerCaughtUpWithPending(
    pending: PendingContentSyncEntry,
    serverItem: LibraryItem
): boolean {
    if (pending.mode === "HIGHLIGHTS") {
        return (
            JSON.stringify(
                normalizeComparableHighlights(pending.snapshot.highlights || [])
            ) ===
            JSON.stringify(
                normalizeComparableHighlights(serverItem.highlights || [])
            )
        );
    }

    const sameCoreFields =
        normalizeMaybeText(serverItem.title) === normalizeMaybeText(pending.snapshot.title) &&
        normalizeMaybeText(serverItem.author) === normalizeMaybeText(pending.snapshot.author) &&
        normalizeMaybeText(serverItem.translator) === normalizeMaybeText(pending.snapshot.translator) &&
        normalizeMaybeText(serverItem.publisher) === normalizeMaybeText(pending.snapshot.publisher) &&
        normalizeMaybeText(serverItem.publicationYear) === normalizeMaybeText(pending.snapshot.publicationYear) &&
        normalizeMaybeText(serverItem.isbn) === normalizeMaybeText(pending.snapshot.isbn) &&
        normalizeMaybeText(serverItem.url) === normalizeMaybeText(pending.snapshot.url) &&
        normalizeMaybeText(serverItem.status) === normalizeMaybeText(pending.snapshot.status) &&
        normalizeMaybeText(serverItem.readingStatus) === normalizeMaybeText(pending.snapshot.readingStatus) &&
        JSON.stringify(normalizeTagList(serverItem.tags)) === JSON.stringify(normalizeTagList(pending.snapshot.tags)) &&
        JSON.stringify(normalizeStringList(serverItem.castTop)) === JSON.stringify(normalizeStringList(pending.snapshot.castTop)) &&
        normalizeMaybeText(serverItem.generalNotes) === normalizeMaybeText(pending.snapshot.generalNotes) &&
        normalizeMaybeText(serverItem.summaryText) === normalizeMaybeText(pending.snapshot.summaryText) &&
        normalizeMaybeText(serverItem.coverUrl) === normalizeMaybeText(pending.snapshot.coverUrl) &&
        normalizeMaybeNumber(serverItem.pageCount) === normalizeMaybeNumber(pending.snapshot.pageCount) &&
        normalizeMaybeText(serverItem.contentLanguageMode) === normalizeMaybeText(pending.snapshot.contentLanguageMode) &&
        normalizeMaybeText(serverItem.contentLanguageResolved) === normalizeMaybeText(pending.snapshot.contentLanguageResolved) &&
        normalizeMaybeText(serverItem.sourceLanguageHint) === normalizeMaybeText(pending.snapshot.sourceLanguageHint) &&
        normalizeMaybeText(serverItem.languageDecisionReason) === normalizeMaybeText(pending.snapshot.languageDecisionReason) &&
        normalizeMaybeNumber(serverItem.languageDecisionConfidence) === normalizeMaybeNumber(pending.snapshot.languageDecisionConfidence);

    if (pending.mode === "ITEM") {
        return sameCoreFields;
    }

    return (
        sameCoreFields &&
        normalizeMaybeText(serverItem.personalNoteCategory) === normalizeMaybeText(pending.snapshot.personalNoteCategory) &&
        normalizeMaybeText(serverItem.personalFolderId) === normalizeMaybeText(pending.snapshot.personalFolderId) &&
        normalizeMaybeText(serverItem.folderPath) === normalizeMaybeText(pending.snapshot.folderPath)
    );
}

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface UseLibrarySyncReturn {
    /** Mark an item as having a pending local mutation (to protect from polling overwrites). */
    markPendingContentSync: (mode: PendingContentSyncMode, snapshot: LibraryItem) => void;
    /** Clear a pending sync entry. */
    clearPendingContentSync: (itemId: string) => void;
    /** Wrap a mutating async task so polling is paused during its execution. */
    runWithMutationLock: <T>(task: () => Promise<T>) => Promise<T>;
    /** Apply local pending overrides to a list of server-fetched items. */
    applyPendingContentSyncOverrides: (serverItems: LibraryItem[]) => LibraryItem[];
    /** Mark an item id as recently deleted (prevents ghost re-render from polling). */
    markRecentlyDeleted: (id: string) => void;
    /** Unmark an item id as recently deleted (used on delete rollback). */
    unmarkRecentlyDeleted: (id: string) => void;
    /** Fetch fresh data from server, applying pending sync overrides and filtering deleted ids. */
    refreshLibraryFromServer: (
        setBooks: React.Dispatch<React.SetStateAction<LibraryItem[]>>,
        setPersonalNoteFolders: React.Dispatch<React.SetStateAction<PersonalNoteFolder[]>>,
        setLastDoc: React.Dispatch<React.SetStateAction<OracleListCursor | null>>,
        setHasMore: React.Dispatch<React.SetStateAction<boolean>>,
    ) => Promise<void>;
    /** Start realtime polling (call in useEffect). Returns cleanup function. */
    startRealtimePolling: (
        setBooks: React.Dispatch<React.SetStateAction<LibraryItem[]>>,
        setPersonalNoteFolders: React.Dispatch<React.SetStateAction<PersonalNoteFolder[]>>,
        setLastDoc: React.Dispatch<React.SetStateAction<OracleListCursor | null>>,
        setHasMore: React.Dispatch<React.SetStateAction<boolean>>,
    ) => () => void;
}

// ---------------------------------------------------------------------------
// useLibrarySync hook
// ---------------------------------------------------------------------------

export function useLibrarySync(userId: string): UseLibrarySyncReturn {
    const pendingContentSyncRef = useRef<Map<string, PendingContentSyncEntry>>(new Map());
    const mutationInFlightCountRef = useRef(0);
    const recentlyDeletedIdsRef = useRef<Set<string>>(new Set());
    const realtimeCursorRef = useRef<number>(0);
    const realtimeInFlightRef = useRef(false);

    // Cleanup pending timers on unmount
    useEffect(() => {
        return () => {
            for (const entry of pendingContentSyncRef.current.values()) {
                window.clearTimeout(entry.timerId);
            }
            pendingContentSyncRef.current.clear();
        };
    }, []);

    const clearPendingContentSync = useCallback((itemId: string) => {
        const pending = pendingContentSyncRef.current.get(itemId);
        if (!pending) return;
        window.clearTimeout(pending.timerId);
        pendingContentSyncRef.current.delete(itemId);
    }, []);

    const markPendingContentSync = useCallback(
        (mode: PendingContentSyncMode, snapshot: LibraryItem) => {
            clearPendingContentSync(snapshot.id);
            const timerId = window.setTimeout(() => {
                pendingContentSyncRef.current.delete(snapshot.id);
            }, 180_000);
            pendingContentSyncRef.current.set(snapshot.id, { mode, snapshot, timerId });
        },
        [clearPendingContentSync]
    );

    const runWithMutationLock = useCallback(
        async <T,>(task: () => Promise<T>): Promise<T> => {
            mutationInFlightCountRef.current += 1;
            try {
                return await task();
            } finally {
                mutationInFlightCountRef.current = Math.max(0, mutationInFlightCountRef.current - 1);
            }
        },
        []
    );

    const applyPendingContentSyncOverrides = useCallback(
        (serverItems: LibraryItem[]): LibraryItem[] => {
            if (pendingContentSyncRef.current.size === 0) return serverItems;
            const pendingResolvedIds: string[] = [];

            const merged = serverItems.map((serverItem) => {
                const pending = pendingContentSyncRef.current.get(serverItem.id);
                if (!pending) return serverItem;

                if (isServerCaughtUpWithPending(pending, serverItem)) {
                    pendingResolvedIds.push(serverItem.id);
                    return serverItem;
                }

                if (pending.mode === "HIGHLIGHTS") {
                    return { ...serverItem, highlights: pending.snapshot.highlights };
                }

                const itemOverlay: LibraryItem = {
                    ...serverItem,
                    title: pending.snapshot.title,
                    author: pending.snapshot.author,
                    translator: pending.snapshot.translator,
                    publisher: pending.snapshot.publisher,
                    publicationYear: pending.snapshot.publicationYear,
                    isbn: pending.snapshot.isbn,
                    url: pending.snapshot.url,
                    status: pending.snapshot.status,
                    readingStatus: pending.snapshot.readingStatus,
                    tags: pending.snapshot.tags,
                    castTop: pending.snapshot.castTop,
                    generalNotes: pending.snapshot.generalNotes,
                    summaryText: pending.snapshot.summaryText,
                    coverUrl: pending.snapshot.coverUrl,
                    pageCount: pending.snapshot.pageCount,
                    contentLanguageMode: pending.snapshot.contentLanguageMode,
                    contentLanguageResolved: pending.snapshot.contentLanguageResolved,
                    sourceLanguageHint: pending.snapshot.sourceLanguageHint,
                    languageDecisionReason: pending.snapshot.languageDecisionReason,
                    languageDecisionConfidence: pending.snapshot.languageDecisionConfidence,
                };

                if (pending.mode === "ITEM") return itemOverlay;

                return {
                    ...itemOverlay,
                    personalNoteCategory: pending.snapshot.personalNoteCategory,
                    personalFolderId: pending.snapshot.personalFolderId,
                    folderPath: pending.snapshot.folderPath,
                };
            });

            if (pendingResolvedIds.length > 0) {
                pendingResolvedIds.forEach((id) => clearPendingContentSync(id));
            }
            return merged;
        },
        [clearPendingContentSync]
    );

    const markRecentlyDeleted = useCallback((id: string) => {
        recentlyDeletedIdsRef.current.add(id);
        setTimeout(() => recentlyDeletedIdsRef.current.delete(id), 10_000);
    }, []);

    const unmarkRecentlyDeleted = useCallback((id: string) => {
        recentlyDeletedIdsRef.current.delete(id);
    }, []);

    const refreshLibraryFromServer = useCallback(
        async (
            setBooks: React.Dispatch<React.SetStateAction<LibraryItem[]>>,
            setPersonalNoteFolders: React.Dispatch<React.SetStateAction<PersonalNoteFolder[]>>,
            setLastDoc: React.Dispatch<React.SetStateAction<OracleListCursor | null>>,
            setHasMore: React.Dispatch<React.SetStateAction<boolean>>,
        ) => {
            const [{ items, lastDoc: newLastDoc }, folders] = await Promise.all([
                fetchItemsForUser(userId),
                fetchPersonalNoteFoldersForUser(userId),
            ]);
            const deletedIds = recentlyDeletedIdsRef.current;
            const safeItems = deletedIds.size > 0 ? items.filter((i) => !deletedIds.has(i.id)) : items;
            const nextItems = applyPendingContentSyncOverrides(safeItems);
            setBooks((previousItems) => reconcileItemsWithPrevious(previousItems, nextItems));
            setPersonalNoteFolders((previousFolders) =>
                reconcileFoldersWithPrevious(previousFolders, folders)
            );
            setLastDoc(newLastDoc);
            setHasMore(!!newLastDoc);
        },
        [applyPendingContentSyncOverrides, userId]
    );

    const startRealtimePolling = useCallback(
        (
            setBooks: React.Dispatch<React.SetStateAction<LibraryItem[]>>,
            setPersonalNoteFolders: React.Dispatch<React.SetStateAction<PersonalNoteFolder[]>>,
            setLastDoc: React.Dispatch<React.SetStateAction<OracleListCursor | null>>,
            setHasMore: React.Dispatch<React.SetStateAction<boolean>>,
        ): (() => void) => {
            let cancelled = false;
            let timerId: number | null = null;
            let realtimeDisabled = false;

            realtimeCursorRef.current = Date.now();
            realtimeInFlightRef.current = false;

            const scheduleNext = () => {
                if (cancelled) return;
                const hidden = typeof document !== "undefined" && document.visibilityState === "hidden";
                const delay = hidden ? 30_000 : 8_000;
                timerId = window.setTimeout(() => {
                    void pollOnce();
                }, delay);
            };

            const pollOnce = async () => {
                if (cancelled || realtimeInFlightRef.current) {
                    scheduleNext();
                    return;
                }
                if (mutationInFlightCountRef.current > 0) {
                    scheduleNext();
                    return;
                }
                realtimeInFlightRef.current = true;

                try {
                    const response = await pollRealtimeEvents(userId, realtimeCursorRef.current, 100);
                    const events = response.events || [];
                    const latestEventTs = events.reduce((maxTs, event) => {
                        const ts = Number(event.updated_at_ms || 0);
                        return ts > maxTs ? ts : maxTs;
                    }, 0);
                    realtimeCursorRef.current = Math.max(
                        realtimeCursorRef.current,
                        Number(response.server_time_ms || 0),
                        latestEventTs
                    );

                    if (events.length > 0) {
                        const [{ items, lastDoc: newLastDoc }, folders] = await Promise.all([
                            fetchItemsForUser(userId),
                            fetchPersonalNoteFoldersForUser(userId),
                        ]);
                        if (!cancelled) {
                            const deletedIds = recentlyDeletedIdsRef.current;
                            const safeItems = deletedIds.size > 0 ? items.filter((i) => !deletedIds.has(i.id)) : items;
                            const nextItems = applyPendingContentSyncOverrides(safeItems);
                            setBooks((previousItems) => reconcileItemsWithPrevious(previousItems, nextItems));
                            setPersonalNoteFolders((previousFolders) =>
                                reconcileFoldersWithPrevious(previousFolders, folders)
                            );
                            setLastDoc(newLastDoc);
                            setHasMore(!!newLastDoc);
                        }
                    }
                } catch (err) {
                    if (err instanceof Error && err.message === "REALTIME_ENDPOINT_NOT_FOUND") {
                        realtimeDisabled = true;
                        console.warn("Realtime polling disabled: endpoint is not available on current backend.");
                        return;
                    }
                    console.warn("Realtime polling failed (non-critical):", err);
                } finally {
                    realtimeInFlightRef.current = false;
                    if (realtimeDisabled) return;
                    scheduleNext();
                }
            };

            const onVisibilityChange = () => {
                if (timerId !== null) window.clearTimeout(timerId);
                scheduleNext();
            };

            scheduleNext();
            document.addEventListener("visibilitychange", onVisibilityChange);

            return () => {
                cancelled = true;
                if (timerId !== null) window.clearTimeout(timerId);
                document.removeEventListener("visibilitychange", onVisibilityChange);
            };
        },
        [applyPendingContentSyncOverrides, userId]
    );

    return {
        markPendingContentSync,
        clearPendingContentSync,
        runWithMutationLock,
        applyPendingContentSyncOverrides,
        markRecentlyDeleted,
        unmarkRecentlyDeleted,
        refreshLibraryFromServer,
        startRealtimePolling,
    };
}
