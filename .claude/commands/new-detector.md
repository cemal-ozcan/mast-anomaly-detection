---
description: Yeni bir anomali dedektörü ekle
---

# Yeni Dedektör Ekleme

Kullanıcı yeni bir anomali dedektörü eklemek istiyor. Aşağıdaki adımları izle.

## Sorulacaklar

1. Dedektör tipi nedir? (rule-based / statistical / ml)
2. Dedektörün adı ve neyi tespit ettiği?
3. Hangi sensör veya sensörler üzerinde çalışacak?
4. Tetiklenme mantığı (eşik değerleri, kurallar, vb.)?

## Yapılacaklar

1. Uygun klasörü belirle:
   - Rule-based: `src/detectors/rules/`
   - Statistical: `src/detectors/statistical/`
   - ML-based: `src/detectors/ml/`

2. `Detector` abstract class'ını implement eden yeni bir dosya oluştur (`<detector_name>_detector.py`).

3. Dedektörün yapılandırılabilir parametrelerini `config/detectors.yaml` içine ekle.

4. `tests/unit/detectors/` altında karşılık gelen test dosyasını oluştur.
   - Normal veri ile false positive üretmediğini test et
   - Bilinen bir arıza senaryosu ile gerçek pozitif ürettiğini test et

5. Eğer yeni dedektör mimari kararı gerektiriyorsa `docs/ARCHITECTURE.md`'yi güncelle.

6. Hatırlat: Yeni dedektör eklendiğinde Alert Manager'ın füzyon mantığını yeniden değerlendirmek gerekebilir.

## Disiplin

- Hard-coded değer yazma, parametreler yapılandırmadan okunmalı
- Tip ipuçları zorunlu
- Docstring ile dedektörün ne yaptığını açıkla
- Detector arayüzünün dışına çıkma (`detect()` metodu)
