import { PersonalNoteCategory } from "../types";

export interface PersonalNoteTemplate {
  id: string;
  name: string;
  suggestedTitle: string;
  defaultCategory: PersonalNoteCategory;
  defaultTags: string[];
  htmlContent: string;
}

export const PERSONAL_NOTE_TEMPLATES: PersonalNoteTemplate[] = [
  {
    id: "shopping_list",
    name: "Alisveris Listesi",
    suggestedTitle: "Alisveris Listesi",
    defaultCategory: "DAILY",
    defaultTags: ["alisveris", "ev", "plan"],
    htmlContent:
      "<h2>Alinacaklar</h2><ul data-type=\"taskList\"><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Market</p></div></li><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Mutfak</p></div></li></ul><h2>Notlar</h2><p></p>",
  },
  {
    id: "word_translation",
    name: "Kelime-Anlam-Ceviri",
    suggestedTitle: "Kelime Notu",
    defaultCategory: "IDEAS",
    defaultTags: ["kelime", "ceviri", "dil"],
    htmlContent:
      "<h2>Kelime</h2><p></p><h2>Anlam</h2><p></p><h2>Ornek Cumle</h2><p></p><h2>Ceviri</h2><p></p>",
  },
  {
    id: "movie_note",
    name: "Film Notu",
    suggestedTitle: "Film Notu",
    defaultCategory: "IDEAS",
    defaultTags: ["film", "inceleme", "izleme"],
    htmlContent:
      "<h2>Film Bilgisi</h2><ul><li>Ad:</li><li>Yonetmen:</li><li>Tur:</li></ul><h2>Ozet</h2><p></p><h2>Degerlendirme</h2><ul><li>Artılar:</li><li>Eksiler:</li></ul><h2>Puan</h2><p>/10</p>",
  },
  {
    id: "series_tracker",
    name: "Dizi Takip",
    suggestedTitle: "Dizi Takip Notu",
    defaultCategory: "DAILY",
    defaultTags: ["dizi", "takip", "izleme"],
    htmlContent:
      "<h2>Genel Bilgi</h2><ul><li>Dizi:</li><li>Sezon:</li><li>Bolum:</li></ul><h2>Takip Listesi</h2><ul data-type=\"taskList\"><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Yeni bolumu izle</p></div></li><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Kisa not al</p></div></li></ul>",
  },
  {
    id: "book_note",
    name: "Kitap Notu",
    suggestedTitle: "Kitap Notu",
    defaultCategory: "IDEAS",
    defaultTags: ["kitap", "okuma", "ozet"],
    htmlContent:
      "<h2>Kitap Bilgisi</h2><ul><li>Baslik:</li><li>Yazar:</li></ul><h2>Ana Fikir</h2><p></p><h2>Alintilar</h2><ul><li></li></ul><h2>Uygulanabilir Notlar</h2><ul data-type=\"taskList\"><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Bir aksiyon yaz</p></div></li></ul>",
  },
  {
    id: "article_note",
    name: "Makale Ozeti",
    suggestedTitle: "Makale Ozeti",
    defaultCategory: "IDEAS",
    defaultTags: ["makale", "arastirma", "ozet"],
    htmlContent:
      "<h2>Kaynak</h2><p>Baslik / Yazar / Link</p><h2>Temel Arguman</h2><p></p><h2>Kritik Bulgular</h2><ol><li></li></ol><h2>Sende Uyandirdigi Sorular</h2><ul><li></li></ul>",
  },
  {
    id: "meeting_note",
    name: "Toplanti Notu",
    suggestedTitle: "Toplanti Notu",
    defaultCategory: "DAILY",
    defaultTags: ["toplanti", "aksiyon", "is"],
    htmlContent:
      "<h2>Toplanti Bilgisi</h2><ul><li>Tarih:</li><li>Katilimcilar:</li></ul><h2>Kararlar</h2><ul><li></li></ul><h2>Aksiyonlar</h2><ul data-type=\"taskList\"><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Aksiyon sahibi - tarih</p></div></li></ul>",
  },
  {
    id: "daily_plan",
    name: "Gunluk Plan",
    suggestedTitle: "Gunluk Plan",
    defaultCategory: "DAILY",
    defaultTags: ["gunluk", "plan", "oncelik"],
    htmlContent:
      "<h2>Oncelikler</h2><ol><li></li></ol><h2>Yapilacaklar</h2><ul data-type=\"taskList\"><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Sabah</p></div></li><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Ogle</p></div></li><li data-checked=\"false\"><label><input type=\"checkbox\"></label><div><p>Aksam</p></div></li></ul><h2>Kisa Not</h2><p></p>",
  },
];

export function findPersonalNoteTemplate(id: string): PersonalNoteTemplate | undefined {
  return PERSONAL_NOTE_TEMPLATES.find((template) => template.id === id);
}
