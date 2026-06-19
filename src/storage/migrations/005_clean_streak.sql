-- Iter 8.7 deadband hysteresis: clean_streak = acik uyarinin ardisik temiz (firing-olmayan) poll
-- sayisi. firing sifirlar, temiz poll artirir, deadband_clean_polls degerine ulasinca resolve (anti-flap).
-- NOT: bu yorumda noktali virgul KULLANMA -- migrator statementlari noktali virgulle boler (naif split).
ALTER TABLE anomalies ADD COLUMN clean_streak INTEGER NOT NULL DEFAULT 0;
