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
    id: "daily_plan",
    name: "Günlük Plan",
    suggestedTitle: "Günlük Plan",
    defaultCategory: "DAILY",
    defaultTags: ["günlük", "plan", "öncelik"],
    htmlContent: `<h2>🎯 Bugünün 3 Önceliği</h2><ol><li><p></p></li><li><p></p></li><li><p></p></li></ol><h2>✅ Yapılacaklar</h2><ul data-type="taskList"><li data-checked="false"><label><input type="checkbox"></label><div><p>Sabah</p></div></li><li data-checked="false"><label><input type="checkbox"></label><div><p>Öğle</p></div></li><li data-checked="false"><label><input type="checkbox"></label><div><p>Akşam</p></div></li></ul><h2>💭 Günün Notu</h2><p></p>`,
  },
  {
    id: "book_note",
    name: "Kitap Notu",
    suggestedTitle: "Kitap Notu",
    defaultCategory: "IDEAS",
    defaultTags: ["kitap", "okuma", "özet"],
    htmlContent: `<h2>📖 Kitap Bilgisi</h2><ul><li>Başlık: </li><li>Yazar: </li><li>Tür: </li></ul><h2>🔑 Ana Fikir</h2><p></p><h2>💡 Önemli Alıntılar</h2><ul><li><p></p></li><li><p></p></li></ul><h2>🚀 Uygulanabilir Çıkarımlar</h2><ul data-type="taskList"><li data-checked="false"><label><input type="checkbox"></label><div><p></p></div></li></ul><h2>⭐ Puan</h2><p> / 10</p>`,
  },
  {
    id: "article_note",
    name: "Makale Özeti",
    suggestedTitle: "Makale Özeti",
    defaultCategory: "IDEAS",
    defaultTags: ["makale", "araştırma", "özet"],
    htmlContent: `<h2>📄 Kaynak</h2><p>Başlık: </p><p>Yazar / Tarih: </p><p>Link: </p><h2>🎯 Temel Argüman</h2><p></p><h2>📊 Kritik Bulgular</h2><ol><li><p></p></li><li><p></p></li><li><p></p></li></ol><h2>❓ Aklıma Düşen Sorular</h2><ul><li><p></p></li></ul><h2>🔗 Bağlantılı Fikirler</h2><p></p>`,
  },
  {
    id: "meeting_note",
    name: "Toplantı Notu",
    suggestedTitle: "Toplantı Notu",
    defaultCategory: "DAILY",
    defaultTags: ["toplantı", "aksiyon", "iş"],
    htmlContent: `<h2>📅 Toplantı Bilgisi</h2><ul><li>Tarih: </li><li>Katılımcılar: </li><li>Konu: </li></ul><h2>📝 Notlar</h2><p></p><h2>✅ Kararlar ve Aksiyonlar</h2><ul data-type="taskList"><li data-checked="false"><label><input type="checkbox"></label><div><p> — sorumlu: , tarih: </p></div></li></ul><h2>📌 Sonraki Adım</h2><p></p>`,
  },
  {
    id: "idea_capture",
    name: "Fikir Kaydı",
    suggestedTitle: "Fikir",
    defaultCategory: "IDEAS",
    defaultTags: ["fikir", "brainstorm", "proje"],
    htmlContent: `<h2>💡 Fikir</h2><p></p><h2>🤔 Neden Önemli?</h2><p></p><h2>🛠️ Nasıl Hayata Geçirilebilir?</h2><ol><li><p></p></li><li><p></p></li></ol><h2>⚡ Hızlı Aksiyon</h2><ul data-type="taskList"><li data-checked="false"><label><input type="checkbox"></label><div><p></p></div></li></ul>`,
  },
  {
    id: "word_translation",
    name: "Kelime Notu",
    suggestedTitle: "Kelime Notu",
    defaultCategory: "IDEAS",
    defaultTags: ["kelime", "çeviri", "dil"],
    htmlContent: `<h2>📝 Kelime</h2><p></p><h2>🌍 Dil / Kaynak</h2><p></p><h2>📖 Anlam</h2><p></p><h2>📌 Örnek Cümle</h2><ul><li><p></p></li><li><p></p></li></ul><h2>🔗 İlişkili Kelimeler</h2><p></p>`,
  },
  {
    id: "movie_note",
    name: "Film / Dizi Notu",
    suggestedTitle: "Film Notu",
    defaultCategory: "IDEAS",
    defaultTags: ["film", "dizi", "inceleme"],
    htmlContent: `<h2>🎬 Bilgi</h2><ul><li>Ad: </li><li>Yönetmen / Yapımcı: </li><li>Tür: </li><li>Yıl: </li></ul><h2>📖 Özet (spoilersız)</h2><p></p><h2>💬 En Beğendiğim Sahne / Diyalog</h2><p></p><h2>🌟 Değerlendirme</h2><ul><li>Artılar: </li><li>Eksiler: </li><li>Puan: /10</li></ul>`,
  },
  {
    id: "shopping_list",
    name: "Alışveriş Listesi",
    suggestedTitle: "Alışveriş",
    defaultCategory: "DAILY",
    defaultTags: ["alışveriş", "liste", "ev"],
    htmlContent: `<h2>🛒 Market</h2><ul data-type="taskList"><li data-checked="false"><label><input type="checkbox"></label><div><p></p></div></li><li data-checked="false"><label><input type="checkbox"></label><div><p></p></div></li><li data-checked="false"><label><input type="checkbox"></label><div><p></p></div></li></ul><h2>🏠 Ev / Diğer</h2><ul data-type="taskList"><li data-checked="false"><label><input type="checkbox"></label><div><p></p></div></li></ul><h2>📌 Notlar</h2><p></p>`,
  },
];

export function findPersonalNoteTemplate(id: string): PersonalNoteTemplate | undefined {
  return PERSONAL_NOTE_TEMPLATES.find((template) => template.id === id);
}
