# Domain — Sektör Bilgisi

Bu doküman endüstriyel teleskopik mast cihazları hakkında çalışma sürecinde kullanılacak nötr, sentetik domain bilgisini içerir. Hiçbir gerçek üretici, model, müşteri veya seri numarası burada yer almaz.

---

## Teleskopik Mast Nedir

Teleskopik mast, içi içe geçmiş silindirik bölmelerden oluşan, kontrollü bir mekanizma ile dikey olarak uzayıp kısalabilen bir taşıyıcı yapıdır. Üzerine antenler, kameralar, ışıklar, sensörler gibi yükler monte edilebilir. Sahada ihtiyaç olduğunda yükseltilir, taşınma sırasında toplanır.

Tahrik mekanizması genellikle elektrikli motor + dişli sistemi veya hidrolik silindirler ile sağlanır. Modern mastlarda her ikisinin kombinasyonu da görülür.

---

## Tipik Sensör Listesi

Bir teleskopik mast sisteminde aşağıdaki kategorilerde sensörler bulunur. Bu liste sentetik veri üretiminde referans olarak kullanılır.

**Motor sensörleri:**
- Motor akımı (A)
- Motor gerilimi (V)
- Motor sıcaklığı (°C)
- Motor devri (RPM)

**Hidrolik sistem sensörleri (varsa):**
- Hidrolik basınç (bar)
- Hidrolik akış (L/dk)
- Yağ sıcaklığı (°C)
- Yağ seviyesi (%)

**Mekanik sensörler:**
- Mast pozisyonu / yükseklik (mm veya m)
- Yükselme/inme hızı (mm/sn)
- Titreşim (g, ivme)
- Çevresel sıcaklık (°C)

**Elektriksel sensörler:**
- Besleme gerilimi (V)
- Toplam akım çekişi (A)
- Güç tüketimi (W)

**Kontrol sinyalleri:**
- Yükselme komutu (boolean)
- İnme komutu (boolean)
- Acil durdurma (boolean)
- Hedef pozisyon (mm)

**Çevresel sensörler:**
- Rüzgar hızı (varsa, m/s)
- Eğim/inklinometre (°)

---

## Sensör Davranış Profilleri (Sentetik Modelleme İçin)

Sentetik veri üretirken her sensörün şu özelliklere sahip olması gerçekçidir.

**Motor akımı:** Mast hareket etmediğinde 0-1A civarı (sadece kontrol elektroniği). Hareket başlarken kısa süreli "inrush current" tepe değeri (5-10x nominal). Hareket boyunca yüke göre 5-15A arası kararlı tüketim. Hareket bitince hızla düşüş.

**Hidrolik basınç:** Boşta düşük (5-20 bar). Hareket başlarken hızlı yükseliş (100-200 bar). Sabit yükseklikte tutarken yüke göre değişken (50-150 bar). Sızıntı durumunda kademeli düşüş.

**Mast pozisyonu:** Doğrusal artış/azalış grafikleri. İdeal hızda eğim sabit. Direnç artarsa eğim azalır (yavaşlama).

**Titreşim:** Hareket halinde temel titreşim seviyesi (0.1-0.5g RMS). Sabit durumda çok düşük. Mekanik aşınma arttıkça titreşim genel olarak artar, spektral imza değişir.

**Sıcaklık:** Yavaş değişen değişken. Çevre sıcaklığına bağlı baseline. Motor/yağ sıcaklığı çalışma süresine bağlı olarak yükselir, çalışma durduğunda yavaşça soğur.

---

## Tipik Arıza Senaryoları

Sentetik veri üretiminde bu senaryolar simüle edilir. Her senaryonun karakteristik bir sensör imzası vardır.

### Senaryo A: Mekanik Aşınma / Sürtünme Artışı

**Fiziksel olay:** Dişli, kayar yatak veya rulman üzerinde kademeli aşınma. Sürtünme katsayısı zamanla artıyor.

**Sensör imzası:**
- Motor akımı normalin %15-30 üzerine çıkıyor (aynı işi yapmak için daha fazla güç)
- Mast yükselme süresi uzuyor (%10-25 daha yavaş)
- Titreşim seviyesi belirgin artıyor
- Motor sıcaklığı normalden yüksek

**Tipik gelişim süresi:** Günler / haftalar (yavaş ilerleyen)

### Senaryo B: Hidrolik Kaçak

**Fiziksel olay:** Conta aşınması veya bağlantı gevşemesi sonucu hidrolik sıvı sızıntısı.

**Sensör imzası:**
- Hidrolik basınç sabit yüksekliği tutarken yavaşça düşüyor (önceden tutuyordu)
- Sabit yükseklikte ufak pozisyon kayması (sızıntı nedeniyle çöküş)
- Yağ seviyesi sensörü varsa kademeli düşüş
- Pompa daha sık devreye giriyor (basıncı tutmak için)

**Tipik gelişim süresi:** Saatler / günler

### Senaryo C: Elektriksel Bağlantı Problemi

**Fiziksel olay:** Konnektör oksitlenmesi, gevşek kontak, kablo hasarı.

**Sensör imzası:**
- Motor gerilimi anlık dalgalanmalar gösteriyor
- Akım profilinde düzensiz sıçramalar
- Bazı durumlarda kontrol sinyalleri kayıp/aralıklı geliyor
- Genel besleme akımında parazitler

**Tipik gelişim süresi:** Anlık / saatler (genelde aniden ortaya çıkıyor)

### Senaryo D: Aşırı Yük

**Fiziksel olay:** Mast üzerine tasarımın üzerinde yük binmesi (örneğin buz birikmesi, ek ekipman).

**Sensör imzası:**
- Motor akımı belirgin yüksek
- Hareket hızı normalden yavaş
- Hidrolik basınç tepe değerleri yüksek
- Çevresel sıcaklık düşükse (kış) buz tutmaya işaret olabilir

**Tipik gelişim süresi:** Ani veya kademeli (yük tipine bağlı)

### Senaryo E: Sensör Arızası (False Data)

**Fiziksel olay:** Bir sensörün kendisi arızalanır, anlamsız değer üretir.

**Sensör imzası:**
- Bir sensör fiziksel olarak imkansız değerler veriyor (negatif basınç, aşırı sıcaklık vb.)
- Diğer ilgili sensörler normal davranıyor
- Değer "donmuş" (uzun süre değişmiyor) veya rastgele atlıyor

**Tipik gelişim süresi:** Ani

### Senaryo F: Sıcaklık Aşımı

**Fiziksel olay:** Sürekli çalışma veya yetersiz soğutma sonucu sistem ısınması.

**Sensör imzası:**
- Motor veya yağ sıcaklığı kritik eşiğe yaklaşıyor
- Performans kademeli olarak düşüyor (motor güç kaybı)
- Çevresel sıcaklıkla korelasyon

**Tipik gelişim süresi:** Saatler

---

## Normal Çalışma Döngüsü

Bir teleskopik mastın tipik günlük çalışma profili:

1. **Bekleme:** Mast indirilmiş, tüm sensörler düşük/sıfır değer civarı
2. **Yükselme komutu alındı:** Kısa süreli motor tepe akımı, hidrolik basınç yükselişi
3. **Yükselme aşaması:** Motor sabit yük, pozisyon doğrusal artış (10-60 saniye)
4. **Hedef pozisyona ulaşıldı:** Motor durdu, hidrolik basınç tutucu seviyede
5. **Uzun süreli yüksek kalış:** Sensörlerde küçük dalgalanmalar (rüzgar etkisi vb.)
6. **İnme komutu:** Kontrollü iniş, pozisyon doğrusal azalış
7. **Tekrar bekleme:** Sistem sıfır pozisyonda

Bu döngü günde birkaç kez tekrarlanabilir. Saatlik veri çıktısı bu örüntüleri göstermelidir.

---

## Anomali Tespiti İçin Önemli İçgörüler

**Tekil değer değil, örüntü.** Tek bir yüksek değer hata olmayabilir; ama bir örüntü içinde anormal davranış genelde gerçek bir problemdir. Bu yüzden dedektörler **pencere bazlı** çalışmalı.

**Bağlam önemlidir.** Aynı motor akımı, mast yükseliyorken normal, sabit dururken anormaldir. Bu yüzden dedektörler **kontrol sinyalleriyle birlikte** değerlendirme yapmalı.

**Karşılaştırmalı analiz güçlüdür.** Bir cihazın bugünkü davranışını geçmiş davranışıyla, veya filodaki diğer benzer cihazlarla karşılaştırmak nadir arızaları yakalamada güçlüdür. İleride filoyu büyüttüğümüzde bu yöntem değer kazanacak.

**Gürültü gerçek bir şeydir.** Sensörler her zaman bir miktar ölçüm gürültüsü içerir. Dedektör tasarımında bu gürültüyü "filtreleme" gerekir, yoksa yanlış alarm patlar.

**Çevre etkisi bağlam katmanıdır.** Aynı arıza yazın ve kışın farklı sensör değerleri üretir. İleride çevresel veriyi (sıcaklık, nem) modele girdi olarak eklemek faydalıdır.

---

## Sentetik Veri Üretim Stratejisi

Simulator yazılırken takip edilecek prensipler:

**Fiziksel gerçeklik.** Üretilen veri fiziksel olarak mantıklı olmalı (negatif basınç olmaz, motor durduğunda akım sıfıra yakındır).

**Gürültü ekle.** Gerçek sensörler hiç gürültüsüz değildir. Gauss gürültüsü ekle.

**Korelasyon koru.** Motor akımı yükselince hidrolik basınç da yükselmeli. Sensörler birbirinden bağımsız değil.

**Zaman dinamiği.** Veriler zaman serisi karakterinde olmalı; "sıçrayan" değil, "akan" değişimler.

**Arıza enjeksiyonu kontrollü.** Senaryolar belirli zaman dilimlerinde aktive edilebilmeli, ki etiketli test verisi olarak kullanılabilsin.

**Çoklu cihaz desteği.** Aynı anda birden fazla simüle cihaz çalışabilmeli, her birinin kendine özgü baseline'ı olmalı.
