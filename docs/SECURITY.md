# Güvenlik — Prensipler ve Kurallar

Bu doküman projenin güvenlik prensiplerini ve katı kurallarını tanımlar. Bu kurallar sentetik veri ile çalıştığımız bu prototip aşamasında bile geçerlidir, çünkü ilerideki üretim ortamına geçişte aynı disipline ihtiyacımız olacak. Disiplini şimdi kazanmak, sonra kaybetmemek için kritik.

---

## Temel Felsefe

Bu proje endüstriyel telemetri verisi üzerinde çalışan bir analiz sistemidir. Üretim ortamında bu tür sistemler hassas operasyonel veriyi işler. Geliştirme aşamasında **sentetik veri ile çalışsak bile**, üretim ortamına geçişte sorun çıkarmayacak alışkanlıklar kazanmak için aynı güvenlik prensiplerini uygularız.

---

## Mutlak Kurallar

Bu kurallar pazarlık konusu değildir. İhlal edilirse proje durur ve hatalı durum düzeltilir.

### Kural 1: Gerçek Veri Yok

Bu kod tabanına hiçbir gerçek müşteri telemetri verisi girmez. Geliştirme tamamen `src/simulator/` tarafından üretilen sentetik veri ile yapılır. Eğer ileride gerçek veri ile entegrasyon gerekirse, bu **ayrı bir ortamda** yapılır, bu kod tabanına yansımaz.

### Kural 2: Kimlik Bilgisi Yok

Hiçbir parola, API anahtarı, sertifika, token, bağlantı dizesi koda commit edilmez. Bunlar `.env` dosyasında saklanır ve `.env` dosyası `.gitignore`'dadır. Geliştiriciler için örnek değerler `.env.example` dosyasında durur.

### Kural 3: Müşteri / Firma Bilgisi Yok

Bu kod tabanında veya dokümantasyonda hiçbir gerçek üretici, müşteri, firma, ürün model adı, seri numarası, müşteri sahası, lokasyon bilgisi yer almaz. Tüm referanslar **sektör nötr** ve **jenerik** olmalıdır. "Endüstriyel teleskopik mast" yazabilirsin, "X Firması'nın Y model mastı" yazamazsın.

### Kural 4: Üretim Bağlantısı Yok

Bu kod tabanı **hiçbir gerçek üretim sistemine** bağlanmaz. Dış IP, gerçek MQTT broker, üretim veritabanı, üçüncü parti API'lar yoktur. Her şey lokal ve simüle edilmiş.

### Kural 5: Bulut Servisi Yok

AWS, Azure, GCP, Cloudflare, Vercel, Heroku, hiçbir bulut servisi kullanılmaz. Telemetri verisi (sentetik bile olsa) bulutta işlenmez, bulutta saklanmaz. Tüm hesaplama lokal.

### Kural 6: Yapay Zeka Servisi Yok (Bu Faz İçin)

OpenAI, Anthropic API, Google AI, hiçbir LLM API'ı çağırılmaz. Geliştirme yardımı için Claude Code'u IDE'de kullanmak farklıdır; o senin geliştirme aracın. Ama sistemin **çalışan parçası** olarak hiçbir LLM API'ı kod içinden çağrılmaz.

### Kural 7: Müdahale Yok

Sistem **sadece gözlem modu** çalışır. Hiçbir cihaza komut göndermez, hiçbir parametreyi değiştirmez. Sadece okur, analiz eder, uyarı üretir. Bu prensip ileride üretim ortamına geçildiğinde de korunur.

---

## Geliştirme Pratikleri

### Hassas Veri Yönetimi

Kod yazarken **hassas görünebilecek her şeyi sentetik tut**. Cihaz isimleri "device_001", "device_002" gibi olsun. Sensör isimleri jenerik olsun. Kullanıcı isimleri "user_alice", "user_bob" gibi olsun.

### Logging Disiplini

Loglara hassas veri yazılmaz. Bir veri noktası loglanacaksa, değer değil sadece istatistik veya hash loglanır. Stack trace'ler hassas veri içeriyorsa filtrelenir.

### Git Hijyeni

Her commit öncesi şu kontroller:
- `.env` dosyası commit ediliyor mu? (asla olmamalı)
- `data/` klasörü içinde bir şey commit ediliyor mu? (asla olmamalı)
- Yorum satırlarında hassas bilgi var mı? (TODO'larda firma isimleri vs.)
- Test fixture'larında gerçek veri var mı? (sadece sentetik)

İleride pre-commit hook eklenebilir, ama prototipte manuel disiplin yeterli.

### Bağımlılık Yönetimi

Yeni bir `pip install` öncesi paketin güvenilirliği değerlendirilir. Geniş kullanılan, aktif bakım gören, açık kaynak paketler tercih edilir. Az indirilen, az bakılan paketlerden uzak durulur.

`requirements.txt` her zaman pinli sürümler içerir (`pandas==2.1.0` gibi), `pandas` gibi serbest sürüm değil. Bu, beklenmedik güncellemelerin sürpriz davranış üretmesini engeller.

---

## Geliştirme Ortamı

### Kişisel Bilgisayar Kullanımı

Bu prototip geliştirme aşamasında geliştirici kendi kişisel bilgisayarında (örnek: M1 MacBook) çalışabilir, **çünkü sadece sentetik veri vardır**. Gerçek bir veri buraya gelmediği sürece kişisel makinede çalışmak güvenlik problemi değildir.

Üretim ortamına geçildiğinde durum tamamen değişir: gerçek veri sadece firma onaylı, sertifikalı cihazlarda işlenir. Bu prototipi üretime taşıma süreci ayrı bir güvenlik değerlendirmesi gerektirir.

### IDE ve Yapay Zeka Asistanı

Claude Code gibi IDE entegrasyonlarını kullanmak güvenlidir çünkü:
- Sadece sentetik veri ile çalışıyoruz
- Hiçbir gerçek müşteri/firma bilgisi kod tabanında yok
- Kod kendisi de hassas iş mantığı değil, jenerik bir anomali tespit altyapısı

Eğer ileride hassas algoritma veya patent değeri olan kod yazılırsa, o noktada yapay zeka asistanı kullanımı yeniden değerlendirilir.

### Ağ Bağlantısı

Geliştirme aşamasında internet bağlantısı paket kurulumu ve dokümantasyon erişimi için gereklidir. Bu normaldir. Ancak çalışan sistem (simulator, ingestion, vb.) internet bağlantısına ihtiyaç duymamalıdır. Tüm servisler `localhost` üzerinde çalışır.

---

## Veri Yaşam Döngüsü

### Sentetik Veri Üretimi

Simulator çalıştığında ürettiği veri MQTT broker üzerinden geçer ve `data/` klasöründeki SQLite veritabanına yazılır. Bu klasör `.gitignore`'dadır, commit edilmez.

### Veri Silme

`data/` klasörü her zaman silinebilir. Sentetik veri tekrar üretilebilir olduğu için kalıcı değildir. Veritabanını sıfırlamak istediğinde `rm -rf data/*.db` yeterlidir.

### Backup

Sentetik veri için backup gerekmez. Eğer bir test senaryosunun belirli veri durumu korunacaksa, o veri fixture olarak `tests/fixtures/` altına çıkartılır ve git'e commit edilir (sadece sentetik olduğu için sorun değil).

---

## Açık Kaynak Yayını

Eğer bu proje GitHub gibi public bir platforma açılırsa:

**Yapılır:**
- Sektör nötr başlık ("Industrial Telemetry Anomaly Detection")
- README'de jenerik anlatım
- MIT veya Apache 2.0 lisansı (açık kaynak felsefesine uygun)

**Yapılmaz:**
- Kimden geldiği, hangi firma için yapıldığı anılmaz
- Gerçek dünya kullanım referansları paylaşılmaz
- Müşteri/firma adı geçen issue veya commit yazılmaz

---

## Olası Riskler ve Önlemler

**Risk:** Yanlışlıkla gerçek veri kopyalanır.
**Önlem:** Asla başka bir kaynaktan kopya-yapıştır yapma. Sentetik veri her zaman simulator tarafından **üretilir**, dışarıdan getirilmez.

**Risk:** `.env` dosyasının commit edilmesi.
**Önlem:** `.gitignore`'da net şekilde dışlanır. Her commit öncesi `git status` kontrolü.

**Risk:** Test verisinde gerçek bilgi.
**Önlem:** Test fixture'ları her zaman simulator tarafından üretilir veya el ile sentetik yazılır.

**Risk:** Loglarda hassas bilgi.
**Önlem:** Logger seviyesi production'da `INFO` veya üzeri, debug logları üretime sızmaz. Hassas alan adları loglardan filtrelenir.

**Risk:** Bağımlılıkta güvenlik açığı.
**Önlem:** `pip-audit` veya benzeri araçla periyodik tarama. Sürüm güncellemelerinden önce değişiklik notlarına bakma.

---

## Üretim Geçişi İçin Not

Bu prototip üretim ortamına alınırken aşağıdaki konular ayrıca ele alınır (şu an kapsam dışı):

- Kimlik doğrulama ve yetkilendirme (Active Directory entegrasyonu vb.)
- Şifreleme (TLS, veritabanı şifreleme)
- Audit log ve denetim
- Erişim kontrolü ve role-based access
- Yedekleme ve felaket kurtarma
- Sertifikasyon ve uyum (NATO, KVKK, ITAR vs.)
- Fiziksel güvenlik (hangi sunucuda çalışıyor, kim erişebiliyor)

Bunların hiçbiri prototip kapsamında değildir. Üretim kararı verildiğinde firmanın bilgi güvenliği birimi ile ortak bir geçiş planı yapılır.
