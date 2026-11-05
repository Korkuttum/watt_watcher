<p align="center"><img src="icon.png" width="128" alt="Watt Watcher"></p>

<h1 align="center">Watt Watcher</h1>

<p align="center"><a href="README.md">English</a></p>

<p align="center">
Akıllı prizin watt değerinden <b>çamaşır / bulaşık makinesi, su ısıtıcı, kahve makinesi</b> gibi cihazların
durumunu (çalışıyor, bitti, boşta) çıkaran Home Assistant entegrasyonu.<br>
<i>A Home Assistant integration that turns a smart plug's power reading into an appliance cycle tracker.</i>
</p>

---

## Özellikler

- Herhangi bir **watt (W) sensöründen** çalışır. Bulut yok, tamamen yerel.
- Durumları kendin tanımlarsın: ad, watt eşiği, büyük/küçük, ikon. İlk durum **başlangıç**, son durum **bitiş**.
- **Duraklamaya dayanıklı:** Bulaşık makinesi yıkama arasında dakikalarca 0 W'a düşer. Bu duraklama
  bitiş sayılırsa, makine tekrar ısındığında yeni bir "başladı" bildirimi gelir. Watt Watcher bunu
  **aynı döngünün devamı** (`resumed`) olarak işler, yeni başlangıç saymaz.
- **Sensör kopmasına dayanıklı:** Priz bir an `unavailable` olursa durum sıfırlanmaz.
- **Yeniden başlatmaya dayanıklı:** Yıkama sırasında Home Assistant yeniden başlarsa durum korunur.
- Her cihaz için: güç, durum, döngü süresi ve döngü enerjisi (Wh) sensörleri, bir de "aktif" binary sensörü.
- Otomasyonlar için olaylar: `watt_watcher_started`, `_finished`, `_resumed`, `_idle`, `_state_changed`.

## Kurulum

### HACS (önerilen)
1. HACS → ⋮ → **Özel depolar** → `https://github.com/Korkuttum/watt_watcher` → kategori **Entegrasyon**.
2. **Watt Watcher**'ı indir, Home Assistant'ı yeniden başlat.
3. Ayarlar → Cihazlar ve Hizmetler → **Entegrasyon ekle** → *Watt Watcher*.

### Elle
Son sürümün `watt_watcher.zip` dosyasını [Releases](https://github.com/Korkuttum/watt_watcher/releases) sayfasından indir ve içindekileri `config/custom_components/watt_watcher/` içine aç. Ya da `custom_components/watt_watcher` klasörünü Home Assistant'ın `config/custom_components/` içine kopyala ve yeniden başlat.

## Zamanlamalar

| Ayar | Anlamı | Öneri |
|---|---|---|
| **Başlama gecikmesi** (`active_delay`) | Güç eşiğin üstünde bu kadar kalırsa döngü başlar | 60 sn |
| **Bitiş gecikmesi** (`finished_delay`) | Güç bu kadar düşük kalırsa döngü biter | çamaşır 300 sn, bulaşık 600 sn |
| **Boşta gecikmesi** (`idle_delay`) | "Bitti" durumunun ne kadar gösterileceği | 3600 sn |
| **Devam etme penceresi** (`resume_window`) | Bittikten sonra bu süre içinde güç dönerse yeni başlangıç değil, devam sayılır. `0` = kapalı | 1800 sn |

> **Bitiş gecikmesi nasıl seçilir?** Cihazın en uzun duraklamasından biraz uzun olsun. Güç geçmişine bak
> ve en uzun düşük-güç aralığını bul. Daha kısa seçersen duraklamada da "bitti" olayı gelir, ama
> `resume_window` sayesinde bunu izleyen ısınma yeni bir başlangıç sayılmaz.
> "Bitti" olaylarının hepsini istemiyorsan `finished_delay`'i duraklamalardan uzun tut.

`resume_window` ayarı etkinken "bitti" durumu en az o süre kadar tutulur (`max(idle_delay, resume_window)`).

## Varlıklar

Her cihaz için (adı `Bulaşık Makinesi` ise):

| Varlık | Açıklama |
|---|---|
| `sensor.bulasik_makinesi_power` | Anlık güç (W) |
| `sensor.bulasik_makinesi_status` | Durum (tanımladığın durumlar + `idle`) |
| `sensor.bulasik_makinesi_cycle_duration` | Döngü süresi (dk) |
| `sensor.bulasik_makinesi_cycle_energy` | Döngüde harcanan enerji (Wh) |
| `binary_sensor.bulasik_makinesi_active` | Döngü sürüyor mu (bitti/idle iken kapalı) |

## Olaylar

| Olay | Ne zaman |
|---|---|
| `watt_watcher_started` | Yeni bir döngü başladı (`idle` → aktif). **"Başladı" bildirimi için bunu kullan.** |
| `watt_watcher_finished` | Döngü bitti |
| `watt_watcher_resumed` | "Bitti" görünen cihaz tekrar çalıştı (aynı döngü) |
| `watt_watcher_idle` | Döngü kapandı, cihaz boşta |
| `watt_watcher_state_changed` | Her durum değişimi |

Olay verisi: `name`, `entry_id`, `from`, `to`, `power`, `cycle_duration` (sn), `resume_count`.

### Örnek otomasyon

```yaml
alias: Bulaşık makinesi bildirimleri
triggers:
  - trigger: event
    event_type: watt_watcher_started
    event_data: { name: Bulaşık Makinesi }
    id: started
  - trigger: event
    event_type: watt_watcher_finished
    event_data: { name: Bulaşık Makinesi }
    id: finished
actions:
  - action: notify.mobile_app_telefonum
    data:
      title: Bulaşık makinesi
      message: >
        {{ 'Yıkama başladı.' if trigger.id == 'started' else 'Yıkama tamamlandı.' }}
```

Olay yerine varlık tetikleyicisi kullanmak istersen durum sensöründe `from: idle` kullan, böylece devam
etmeler (`bitti` → `yıkıyor`) tetiklemez:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.bulasik_makinesi_status
    from: idle
```

## Sorun giderme

- **Hâlâ tekrar tekrar "başladı" geliyor:** Otomasyonun `binary_sensor …_active → on` ile tetiklenmediğinden
  emin ol. Duraklamadan sonra bu sensör de açılır. Yukarıdaki olay ya da `from: idle` tetikleyicisini kullan.
- **Bitiş çok geç geliyor:** `finished_delay`'i kısalt, ama duraklamaların altına düşme.
- **Ayrıntılı günlük:**
  ```yaml
  logger:
    logs:
      custom_components.watt_watcher: debug
  ```

## Geliştirme

```bash
python3 tests/test_state_machine.py   # Home Assistant gerekmez
```

## Lisans

[MIT](LICENSE)
