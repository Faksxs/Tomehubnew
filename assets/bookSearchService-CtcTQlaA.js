const m={BASE_URL:"/Tomehubnew/",DEV:!1,MODE:"production",PROD:!0,SSR:!1,VITE_FIREBASE_API_KEY:"AIzaSyDwvjdmQGhwIgAKgaVmOkOnFdMgzaJ4heA",VITE_FIREBASE_APP_ID:"1:407093539608:web:dfd1e04346b49060d2246d",VITE_FIREBASE_AUTH_DOMAIN:"tomehub.firebaseapp.com",VITE_FIREBASE_MESSAGING_SENDER_ID:"407093539608",VITE_FIREBASE_PROJECT_ID:"tomehub",VITE_FIREBASE_STORAGE_BUCKET:"tomehub.firebasestorage.app",VITE_GEMINI_API_KEY:"AIzaSyAv2yz93Gk4KD_5Iabna9_36Q9h9lIt9Os",VITE_PROXY_URL:"http://localhost:3001"};var b={};function T(n){if(typeof process<"u"&&b&&b[n])return b[n];if(typeof import.meta<"u"&&m)return m[`VITE_${n}`]||m[n]}class E{constructor(){this.cache=new Map,this.TTL=1e3*60*60}set(o,t){this.cache.set(o,{data:t,timestamp:Date.now()})}get(o){const t=this.cache.get(o);return t?Date.now()-t.timestamp>this.TTL?(this.cache.delete(o),null):t.data:null}clear(){this.cache.clear()}}const p=new E,_=new E;function d(n){return(n||"").toLowerCase().trim().replace(/\s+/g," ")}function v(n){const o=new Set;o.add(n);const t={ç:"c",ğ:"g",ı:"i",ö:"o",ş:"s",ü:"u",Ç:"C",Ğ:"G",İ:"I",Ö:"O",Ş:"S",Ü:"U"};let e=n;for(const[r,a]of Object.entries(t))e=e.replace(new RegExp(r,"g"),a);return e!==n&&o.add(e),Array.from(o).slice(0,5)}function L(n,o){const t=[];for(let e=0;e<=o.length;e++)t[e]=[e];for(let e=0;e<=n.length;e++)t[0][e]=e;for(let e=1;e<=o.length;e++)for(let r=1;r<=n.length;r++)o.charAt(e-1)===n.charAt(r-1)?t[e][r]=t[e-1][r-1]:t[e][r]=Math.min(t[e-1][r-1]+1,t[e][r-1]+1,t[e-1][r]+1);return t[o.length][n.length]}function w(n,o){const t=d(n),e=d(o);if(!t||!e)return 0;if(t===e)return 1;if(e.includes(t))return .9;const r=Math.max(t.length,e.length);return r===0?0:1-L(t,e)/r}function S(n,o){const e=o.map(r=>{const a=w(n,r.title),i=r.author?w(n,r.author):0,c=Math.max(a,i*.7);return{result:r,score:c}}).filter(r=>r.score>=.3);return e.sort((r,a)=>a.score-r.score),e.map(r=>r.result)}function k(n){const o=new Set,t=[];for(const e of n){const r=`${d(e.title)}|${d(e.author)}`;o.has(r)||(o.add(r),t.push(e))}return t}async function R(n){try{const o=v(n),t=[];for(const e of o){const r=`https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(e)}&maxResults=10`,a=await fetch(r);if(!a.ok)continue;const i=await a.json();if(!i.items)continue;const c=i.items.map(s=>{var u,h,l,f;return{title:s.volumeInfo.title||"",author:((u=s.volumeInfo.authors)==null?void 0:u[0])||"Unknown",publisher:s.volumeInfo.publisher||"",isbn:((l=(h=s.volumeInfo.industryIdentifiers)==null?void 0:h[0])==null?void 0:l.identifier)||"",translator:"",tags:s.volumeInfo.categories||[],summary:s.volumeInfo.description||"",publishedDate:s.volumeInfo.publishedDate||"",url:s.volumeInfo.infoLink||"",coverUrl:((f=s.volumeInfo.imageLinks)==null?void 0:f.thumbnail)||null}});if(t.push(...c),t.length>=3)break}return t}catch(o){return console.error("Google Books error:",o),[]}}async function A(n){try{const o=v(n),t=[];for(const e of o){const r=`https://openlibrary.org/search.json?q=${encodeURIComponent(e)}&limit=10`,a=await fetch(r);if(!a.ok)continue;const i=await a.json();if(!i.docs||i.docs.length===0)continue;const c=i.docs.map(s=>{var u,h,l,f,g;return{title:s.title||"",author:((u=s.author_name)==null?void 0:u[0])||"Unknown",publisher:((h=s.publisher)==null?void 0:h[0])||"",isbn:((l=s.isbn)==null?void 0:l[0])||"",translator:"",tags:((f=s.subject)==null?void 0:f.slice(0,5))||[],summary:"",publishedDate:((g=s.first_publish_year)==null?void 0:g.toString())||"",url:`https://openlibrary.org${s.key}`,coverUrl:s.cover_i?`https://covers.openlibrary.org/b/id/${s.cover_i}-M.jpg`:null}});if(t.push(...c),t.length>=3)break}return t}catch(o){return console.error("Open Library error:",o),[]}}async function x(n){var t,e,r,a,i;const o=_.get(n);if(o)return o;try{const c=T("GEMINI_API_KEY");if(!c)return console.warn("GEMINI_API_KEY not found"),null;const s=`You are an intelligent search optimization engine specialized in books.
Your task is to transform any user-entered search query—no matter how messy—into a clean, corrected, highly accurate search instruction.

The user query may contain:
- Missing or incorrect characters (e.g., diacritics)
- Typos in author names or book titles
- Combined title + author in one string
- Mixed uppercase/lowercase
- Partial or incomplete title/author information

Your job is to fix all of these.

When rewriting the query, follow these rules:

1. Correct all spelling mistakes in book title and author names.
2. Restore missing characters where appropriate.
3. Separate the book title and author, if they appear mixed together.
4. Produce a JSON object with the following structure:

{
  "title": "<corrected full title or null>",
  "author": "<corrected full author name or null>",
  "isbn": "<extract if the user typed an ISBN, otherwise null>",
  "standardized_query": "<API-ready query using filters like intitle:, inauthor:, isbn:>",
  "keywords": "<refined keyword list>",
  "confidence": "<0–100 confidence score>"
}

5. When generating standardized_query, use the most specific filters available:
- If ISBN exists → use isbn:<number>
- If both title and author exist → use: intitle:"<title>" inauthor:"<author>"
- If only title exists → use: intitle:"<title>"
- If only author exists → use: inauthor:"<author>"

6. Normalize casing: output should always be clean and properly capitalized.
7. Avoid hallucinating nonexistent authors or books—ONLY correct what is clearly intended.

Query: "${n}"

Respond with ONLY the JSON described above, with no extra text or explanation.`,u=new AbortController,h=setTimeout(()=>u.abort(),1500),l=await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${c}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({contents:[{parts:[{text:s}]}],generationConfig:{temperature:.1,maxOutputTokens:300,response_mime_type:"application/json"}}),signal:u.signal});if(clearTimeout(h),!l.ok)return null;const I=(((i=(a=(r=(e=(t=(await l.json()).candidates)==null?void 0:t[0])==null?void 0:e.content)==null?void 0:r.parts)==null?void 0:a[0])==null?void 0:i.text)||"").match(/\{[\s\S]*\}/);if(!I)return null;const y=JSON.parse(I[0]);return _.set(n,y),y}catch(c){return console.error("LLM correction error:",c),null}}async function O(n){const o=await x(n);if(!o)return[];let t=o.standardized_query;if(!t){const c=o.title||"",s=o.author||"";t=s?`${c} ${s}`:c||n}const[e,r]=await Promise.all([R(t),A(t)]),a=[...e,...r],i=k(a);return S(n,i).slice(0,10)}async function M(n){if(!n.trim())return{results:[],source:"google-books",cached:!1};const o=d(n),t=`search:${o}`,e=p.get(t);if(e)return console.log("✓ Cache hit for:",o),{...e,cached:!0};console.log("🔍 Searching for:",o);const[r,a]=await Promise.all([R(o),A(o)]);let i=[...r,...a];const c=k(i),s=S(n,c);if(s.length>=3){const l={results:s.slice(0,10),source:r.length>0?"google-books":"open-library",cached:!1};return p.set(t,l),console.log(`✓ Found ${s.length} results from APIs`),l}console.log("⚠ Poor results, trying LLM correction...");const u=await O(o);if(u.length>0){const l={results:u,source:"llm-corrected",cached:!1};return p.set(t,l),console.log(`✓ Found ${u.length} results with LLM correction`),l}const h={results:s,source:"google-books",cached:!1};return p.set(t,h),console.log(`⚠ Returning ${s.length} results (best effort)`),h}export{M as searchBooks};
