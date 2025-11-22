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
} from "firebase/firestore";
import { db } from "./firebaseClient";
import { LibraryItem } from "../types";

// Her kullanıcı için items koleksiyonu
const userItemsCollection = (userId: string) =>
    collection(db, "users", userId, "items");

/**
 * Kullanıcının tüm item'larını Firestore'dan çeker.
 * (Books, Articles, Websites, Personal Notes hepsi dahil)
 */
export const fetchItemsForUser = async (
    userId: string,
    limitCount: number = 600,
    lastDoc?: QueryDocumentSnapshot<DocumentData> | null
): Promise<{ items: LibraryItem[]; lastDoc: QueryDocumentSnapshot<DocumentData> | null }> => {
    let q = query(userItemsCollection(userId), orderBy("addedAt", "desc"), limit(limitCount));

    if (lastDoc) {
        q = query(userItemsCollection(userId), orderBy("addedAt", "desc"), startAfter(lastDoc), limit(limitCount));
    }

    const snapshot = await getDocs(q);

    const items = snapshot.docs.map((docSnap) => {
        const data = docSnap.data() as Omit<LibraryItem, "id">;
        return {
            ...(data as LibraryItem),
            id: docSnap.id, // Firestore doc id → bizim item.id
        };
    });

    const newLastDoc = snapshot.docs.length > 0 ? snapshot.docs[snapshot.docs.length - 1] : null;

    return { items, lastDoc: newLastDoc };
};

/**
 * Bir item'ı Firestore'a kaydeder (yoksa ekler, varsa günceller).
 * Tüm tipler için geçerli: BOOK / ARTICLE / WEBSITE / PERSONAL_NOTE
 */
export const saveItemForUser = async (
    userId: string,
    item: LibraryItem
): Promise<void> => {
    console.log("SAVE ITEM FOR USER →", { userId, item }); // sadece debug için

    const ref = doc(userItemsCollection(userId), item.id);

    // id'yi Firestore'da ayrıca tutmuyoruz, doc id olarak kullanıyoruz
    const { id, ...rest } = item;

    // 🔴 ÖNEMLİ: Firestore 'undefined' alanları kabul etmez.
    // Bu satır, tüm undefined alanları derinlemesine temizler.
    const cleaned = JSON.parse(JSON.stringify(rest));

    await setDoc(ref, cleaned, { merge: true });
    console.log("SAVE OK");
};


/**
 * Bir item'ı Firestore'dan siler.
 */
export const deleteItemForUser = async (
    userId: string,
    itemId: string
): Promise<void> => {
    const ref = doc(userItemsCollection(userId), itemId);
    await deleteDoc(ref);
};
