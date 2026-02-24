import type { QueryDocumentSnapshot, DocumentData } from "firebase/firestore";
import { Highlight, LibraryItem, PersonalNoteCategory, PersonalNoteFolder } from "../types";
import { normalizeHighlightType } from "../lib/highlightType";
import { normalizeFolderPath, normalizePersonalFolderId, normalizePersonalNoteCategory } from "../lib/personalNotePolicy";
import { API_BASE_URL, fetchWithAuth, parseApiErrorMessage } from "./apiClient";

type OracleCursorDoc = QueryDocumentSnapshot<DocumentData> & { __oracleCursor?: string };

const normalizeTimestamp = (value: unknown, fallback: number): number => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
        const parsed = Date.parse(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return fallback;
};

const normalizeContentLanguageMode = (value: unknown): "AUTO" | "TR" | "EN" => {
    const raw = String(value || "AUTO").trim().toUpperCase();
    if (raw === "TR" || raw === "EN") return raw;
    return "AUTO";
};

const normalizeContentLanguageResolved = (value: unknown): "tr" | "en" | undefined => {
    const raw = String(value || "").trim().toLowerCase();
    if (raw === "tr" || raw === "en") return raw;
    return undefined;
};

const normalizeHighlight = (highlight: Partial<Highlight>, index: number): Highlight => {
    const createdAt = normalizeTimestamp(highlight.createdAt, Date.now());
    return {
        id: typeof highlight.id === "string" && highlight.id.trim() ? highlight.id : `${createdAt}-${index}`,
        text: highlight.text || "",
        type: normalizeHighlightType(highlight.type),
        pageNumber: highlight.pageNumber,
        paragraphNumber: highlight.paragraphNumber,
        chapterTitle: highlight.chapterTitle,
        comment: highlight.comment,
        createdAt,
        tags: Array.isArray(highlight.tags) ? highlight.tags : [],
        isFavorite: !!highlight.isFavorite,
    };
};

const normalizeItemShape = (item: LibraryItem): LibraryItem => ({
    ...item,
    addedAt: normalizeTimestamp(item.addedAt, Date.now()),
    tags: Array.isArray(item.tags) ? item.tags : [],
    contentLanguageMode: normalizeContentLanguageMode(item.contentLanguageMode),
    contentLanguageResolved: normalizeContentLanguageResolved(item.contentLanguageResolved),
    sourceLanguageHint: normalizeContentLanguageResolved(item.sourceLanguageHint),
    highlights: Array.isArray(item.highlights)
        ? item.highlights.map((h, index) => normalizeHighlight(h, index))
        : [],
    personalNoteCategory: item.type === "PERSONAL_NOTE"
        ? normalizePersonalNoteCategory(item.personalNoteCategory)
        : undefined,
    personalFolderId: item.type === "PERSONAL_NOTE"
        ? normalizePersonalFolderId(item.personalFolderId)
        : undefined,
    folderPath: item.type === "PERSONAL_NOTE"
        ? normalizeFolderPath(item.folderPath)
        : undefined,
    status: (item.status || "On Shelf") as LibraryItem["status"],
    readingStatus: (item.readingStatus || "To Read") as LibraryItem["readingStatus"],
    author: (item.author || "Unknown Author").trim() || "Unknown Author",
    title: (item.title || "Untitled").trim() || "Untitled",
});

const normalizeFolderShape = (folder: PersonalNoteFolder): PersonalNoteFolder => ({
    ...folder,
    category: normalizePersonalNoteCategory(folder.category),
    name: (folder.name || "").trim(),
    order: Number.isFinite(folder.order) ? folder.order : 0,
    createdAt: normalizeTimestamp(folder.createdAt, Date.now()),
    updatedAt: normalizeTimestamp(folder.updatedAt, Date.now()),
});

function asOracleCursorDoc(cursor?: string | null): OracleCursorDoc | null {
    if (!cursor) return null;
    return { __oracleCursor: cursor } as OracleCursorDoc;
}

function getCursorToken(lastDoc?: QueryDocumentSnapshot<DocumentData> | null): string | undefined {
    if (!lastDoc) return undefined;
    const maybe = lastDoc as OracleCursorDoc;
    return maybe.__oracleCursor;
}

export const fetchItemsForUser = async (
    userId: string,
    limitCount: number = 2000,
    lastDoc?: QueryDocumentSnapshot<DocumentData> | null
): Promise<{ items: LibraryItem[]; lastDoc: QueryDocumentSnapshot<DocumentData> | null }> => {
    const url = new URL(`${API_BASE_URL}/api/library/items`);
    url.searchParams.set("limit", String(limitCount));
    const cursor = getCursorToken(lastDoc);
    if (cursor) url.searchParams.set("cursor", cursor);

    const response = await fetchWithAuth(url.toString());
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to fetch library items from Oracle"));
    }

    const payload = await response.json();
    const rawItems = Array.isArray(payload?.items) ? payload.items : [];
    const items = rawItems.map((raw: any) => normalizeItemShape(raw as LibraryItem));
    const nextLastDoc = asOracleCursorDoc(typeof payload?.next_cursor === "string" ? payload.next_cursor : null);
    return { items, lastDoc: nextLastDoc as QueryDocumentSnapshot<DocumentData> | null };
};

export const saveItemForUser = async (
    userId: string,
    item: LibraryItem
): Promise<void> => {
    void userId; // UID comes from JWT on backend.
    const normalizedItem = normalizeItemShape(item);
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/items/${encodeURIComponent(normalizedItem.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(normalizedItem),
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to save library item to Oracle"));
    }
};

export const deleteItemForUser = async (
    userId: string,
    itemId: string
): Promise<void> => {
    void userId;
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/items/${encodeURIComponent(itemId)}`, {
        method: "DELETE",
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to delete library item from Oracle"));
    }
};

export const deleteMultipleItemsForUser = async (
    userId: string,
    itemIds: string[]
): Promise<void> => {
    void userId;
    if (itemIds.length === 0) return;
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/items/bulk-delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_ids: itemIds }),
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to bulk delete library items from Oracle"));
    }
};

export const fetchPersonalNoteFoldersForUser = async (
    userId: string
): Promise<PersonalNoteFolder[]> => {
    void userId;
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/personal-note-folders`);
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to fetch personal note folders from Oracle"));
    }
    const payload = await response.json();
    const folders = Array.isArray(payload?.folders) ? payload.folders : [];
    return folders.map((f: any) => normalizeFolderShape(f as PersonalNoteFolder)).sort((a, b) => {
        if (a.category !== b.category) return a.category.localeCompare(b.category);
        if (a.order !== b.order) return a.order - b.order;
        return a.name.localeCompare(b.name);
    });
};

export const savePersonalNoteFolderForUser = async (
    userId: string,
    folder: PersonalNoteFolder
): Promise<void> => {
    void userId;
    const normalized = normalizeFolderShape(folder);
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/personal-note-folders/${encodeURIComponent(normalized.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(normalized),
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to save personal note folder to Oracle"));
    }
};

export const updatePersonalNoteFolderForUser = async (
    userId: string,
    folderId: string,
    patch: Partial<Pick<PersonalNoteFolder, "name" | "order" | "category" | "updatedAt">>
): Promise<void> => {
    void userId;
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/personal-note-folders/${encodeURIComponent(folderId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to update personal note folder in Oracle"));
    }
};

export const deletePersonalNoteFolderForUser = async (
    userId: string,
    folderId: string
): Promise<void> => {
    void userId;
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/personal-note-folders/${encodeURIComponent(folderId)}`, {
        method: "DELETE",
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to delete personal note folder from Oracle"));
    }
};

export const movePersonalNoteForUser = async (
    userId: string,
    itemId: string,
    targetCategory: PersonalNoteCategory,
    targetFolderId?: string,
    folderPath?: string
): Promise<void> => {
    void userId;
    const response = await fetchWithAuth(`${API_BASE_URL}/api/library/items/${encodeURIComponent(itemId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            patch: {
                personalNoteCategory: normalizePersonalNoteCategory(targetCategory),
                personalFolderId: normalizePersonalFolderId(targetFolderId) || null,
                folderPath: normalizeFolderPath(folderPath) || null,
            },
        }),
    });
    if (!response.ok) {
        throw new Error(await parseApiErrorMessage(response, "Failed to move personal note in Oracle"));
    }
};

