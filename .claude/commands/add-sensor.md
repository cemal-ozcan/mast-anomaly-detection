---
description: Simulator'a yeni bir sensör tipi ekle
---

# Yeni Sensör Tipi Ekleme

Kullanıcı simulator'a yeni bir sensör tipi eklemek istiyor.

## Sorulacaklar

1. Sensör adı ve birimi nedir? (örnek: "motor_temperature" - °C)
2. Normal çalışma değer aralığı nedir?
3. Gürültü karakteri nedir? (Gauss std değeri)
4. Diğer sensörlerle korelasyonu var mı? (örnek: motor akımı yükselince sıcaklık yükselir)
5. Cihaz hareketsiz vs hareketli durumdaki davranışı farklı mı?

## Yapılacaklar

1. `docs/DOMAIN.md` dosyasındaki "Tipik Sensör Listesi" bölümünü kontrol et, eklenecek sensör listede yoksa ekle.

2. `src/simulator/sensors/` altında yeni sensör sınıfını oluştur. Tüm sensörler aynı `Sensor` arayüzünü implement eder.

3. Sensörün fiziksel davranışını matematiksel olarak modelle:
   - Baseline değeri
   - Gürültü modeli
   - Hareket durumuna göre tepkisi
   - Diğer sensörlerle korelasyon (varsa)

4. `config/devices.yaml` içinde sensörü cihaz tanımlarına ekle.

5. `tests/unit/simulator/` altında sensör için unit test yaz:
   - Üretilen değerler fiziksel olarak makul mü
   - Gürültü dağılımı beklenen aralıkta mı
   - Korelasyonlar korunuyor mu

## Disiplin

- Negatif basınç gibi fiziksel olarak imkansız değerler üretme
- Sensör çıktısı **akar**, sıçramaz (zaman serisi karakterinde)
- Birim her zaman açıkça belirtilir (kod yorumlarında ve docstring'de)
