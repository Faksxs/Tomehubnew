import {
    collection,
    doc,
    getDocs,
    setDoc,
    deleteDoc,
    query,
    orderBy,
    limit,
    startAfter,
    QueryDocumentSnapshot,
    DocumentData,
    writeBatch,
} from "firebase/firestore";
import { db } from "./firebaseClient";
import { Highlight, LibraryItem, PersonalNoteCategory, PersonalNoteFolder } from "../types";
import { normalizeHighlightType } from "../lib/highlightType";
import { normalizeFolderPath, normalizePersonalFolderId, normalizePersonalNoteCategory } from "../lib/personalNotePolicy";

const userItemsCollection = (userId: string) =>
    collection(db, "users", userId, "items");
const userPersonalFoldersCollection = (userId: string) =>
    collection(db, "users", userId, "personalNoteFolders");

const normalizeTimestamp = (value: unknown, fallback: number): number => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
        const parsed = Date.parse(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return fallback;
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
});

const normalizeFolderShape = (folder: PersonalNoteFolder): PersonalNoteFolder => ({
    ...folder,
    category: normalizePersonalNoteCategory(folder.category),
    name: (folder.name || "").trim(),
    order: Number.isFinite(folder.order) ? folder.order : 0,
    createdAt: normalizeTimestamp(folder.createdAt, Date.now()),
    updatedAt: normalizeTimestamp(folder.updatedAt, Date.now()),
});

export const fetchItemsForUser = async (
    userId: string,
    limitCount: number = 2000,
    lastDoc?: QueryDocumentSnapshot<DocumentData> | null
): Promise<{ items: LibraryItem[]; lastDoc: QueryDocumentSnapshot<DocumentData> | null }> => {
    let q = query(userItemsCollection(userId), orderBy("addedAt", "desc"), limit(limitCount));

    if (lastDoc) {
        q = query(userItemsCollection(userId), orderBy("addedAt", "desc"), startAfter(lastDoc), limit(limitCount));
    }

    const snapshot = await getDocs(q);

    const items = snapshot.docs.map((docSnap) => {
        const data = docSnap.data() as Omit<LibraryItem, "id">;
        return normalizeItemShape({
            ...(data as LibraryItem),
            id: docSnap.id,
        });
    });

    const newLastDoc = snapshot.docs.length > 0 ? snapshot.docs[snapshot.docs.length - 1] : null;
    return { items, lastDoc: newLastDoc };
};

export const saveItemForUser = async (
    userId: string,
    item: LibraryItem
): Promise<void> => {
    const normalizedItem = normalizeItemShape(item);
    console.log("SAVE ITEM FOR USER ->", { userId, item: normalizedItem });

    const ref = doc(userItemsCollection(userId), normalizedItem.id);
    const { id, ...rest } = normalizedItem;

    const cleaned = JSON.parse(JSON.stringify(rest));
    await setDoc(ref, cleaned, { merge: true });
    console.log("SAVE OK");
};

export const deleteItemForUser = async (
    userId: string,
    itemId: string
): Promise<void> => {
    const ref = doc(userItemsCollection(userId), itemId);
    await deleteDoc(ref);
    await deleteDoc(ref);
};

export const deleteMultipleItemsForUser = async (
    userId: string,
    itemIds: string[]
): Promise<void> => {
    if (itemIds.length === 0) return;

    const batch = writeBatch(db);
    itemIds.forEach((id) => {
        const ref = doc(userItemsCollection(userId), id);
        batch.delete(ref);
    });
    await batch.commit();
};

export const fetchPersonalNoteFoldersForUser = async (
    userId: string
): Promise<PersonalNoteFolder[]> => {
    const snapshot = await getDocs(userPersonalFoldersCollection(userId));
    const folders = snapshot.docs.map((docSnap) => {
        const data = docSnap.data() as Omit<PersonalNoteFolder, "id">;
        return normalizeFolderShape({
            ...(data as PersonalNoteFolder),
            id: docSnap.id,
        });
    });
    return folders.sort((a, b) => {
        if (a.category !== b.category) return a.category.localeCompare(b.category);
        if (a.order !== b.order) return a.order - b.order;
        return a.name.localeCompare(b.name);
    });
};

export const savePersonalNoteFolderForUser = async (
    userId: string,
    folder: PersonalNoteFolder
): Promise<void> => {
    const normalized = normalizeFolderShape(folder);
    const ref = doc(userPersonalFoldersCollection(userId), normalized.id);
    const { id, ...rest } = normalized;
    const cleaned = JSON.parse(JSON.stringify(rest));
    await setDoc(ref, cleaned, { merge: true });
};

export const updatePersonalNoteFolderForUser = async (
    userId: string,
    folderId: string,
    patch: Partial<Pick<PersonalNoteFolder, "name" | "order" | "category" | "updatedAt">>
): Promise<void> => {
    const ref = doc(userPersonalFoldersCollection(userId), folderId);
    const normalizedPatch: Record<string, unknown> = {
        updatedAt: normalizeTimestamp(patch.updatedAt, Date.now()),
    };
    if (typeof patch.name === "string") normalizedPatch.name = patch.name.trim();
    if (typeof patch.category === "string") normalizedPatch.category = normalizePersonalNoteCategory(patch.category);
    if (typeof patch.order === "number" && Number.isFinite(patch.order)) normalizedPatch.order = patch.order;
    await setDoc(ref, normalizedPatch, { merge: true });
};

export const deletePersonalNoteFolderForUser = async (
    userId: string,
    folderId: string
): Promise<void> => {
    const ref = doc(userPersonalFoldersCollection(userId), folderId);
    await deleteDoc(ref);
};

export const movePersonalNoteForUser = async (
    userId: string,
    itemId: string,
    targetCategory: PersonalNoteCategory,
    targetFolderId?: string,
    folderPath?: string
): Promise<void> => {
    const ref = doc(userItemsCollection(userId), itemId);
    await setDoc(ref, {
        personalNoteCategory: normalizePersonalNoteCategory(targetCategory),
        personalFolderId: normalizePersonalFolderId(targetFolderId) || null,
        folderPath: normalizeFolderPath(folderPath) || null,
    }, { merge: true });
};
