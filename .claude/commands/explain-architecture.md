---
description: Mevcut sistem mimarisini açıkla
---

# Mimari Açıklaması

Kullanıcı sistemin mimarisini anlamak istiyor.

## Yapılacaklar

1. `docs/ARCHITECTURE.md` dosyasını oku.

2. Aşağıdaki konuları **özet ve net** olarak açıkla:
   - Katmanların listesi ve her birinin sorumluluğu
   - Veri akışı diyagramı (ASCII art yeterli)
   - Hangi katman hangi dosyada yaşıyor
   - Servisler arası iletişim nasıl olur (MQTT topic'leri vs.)

3. Eğer kullanıcı belirli bir katman hakkında soru soruyorsa, o katmanın ilgili kod dosyalarını da incele (`src/<katman>/`) ve mevcut implementasyon ile mimari arasındaki tutarlılığı kontrol et.

4. Eğer tutarsızlık varsa kullanıcıyı uyar: "Mimari dokümanı X diyor ama kodda Y görünüyor. Hangisi doğru?"

## Disiplin

- Açıklama uzun olabilir ama **gereksiz** olmasın
- Kod örneği vermek gerekiyorsa kısa tut
- Mimari kararların **gerekçesini** de açıkla, sadece "şu var" deme
