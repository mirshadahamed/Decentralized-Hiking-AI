import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// English, Sinhala and Tamil for the visitor screens.
/// NOTE: the Sinhala and Tamil texts are DRAFTS. They must be checked by native speakers (and park staff for
/// the Sri Pada terms) before the app is shown to the public. Missing keys fall back to English.
class C4Lang extends ChangeNotifier {
  C4Lang([this.code = 'en']);

  static const languages = {'en': 'English', 'si': 'සිංහල', 'ta': 'தமிழ்'};
  static const _key = 'c4_language';

  String code;

  static Future<C4Lang> load() async {
    final p = await SharedPreferences.getInstance();
    final c = p.getString(_key);
    return C4Lang(languages.containsKey(c) ? c! : 'en');
  }

  Future<void> set(String c) async {
    if (c == code || !languages.containsKey(c)) return;
    code = c;
    notifyListeners();
    final p = await SharedPreferences.getInstance();
    await p.setString(_key, c);
  }

  /// Text for [key] with {name} placeholders filled from [args].
  String t(String key, [Map<String, Object> args = const {}]) {
    var s = _strings[key]?[code] ?? _strings[key]?['en'] ?? key;
    args.forEach((k, v) => s = s.replaceAll('{$k}', '$v'));
    return s;
  }
}

const Map<String, Map<String, String>> _strings = {
  // ---------- general ----------
  'choose_park': {'en': 'Choose a place', 'si': 'ස්ථානයක් තෝරන්න', 'ta': 'ஒரு இடத்தைத் தேர்ந்தெடுக்கவும்'},
  'choose_park_sub': {
    'en': 'Crowd forecasts and advice for each site.',
    'si': 'එක් එක් ස්ථානය සඳහා සෙනඟ පුරෝකථන සහ උපදෙස්.',
    'ta': 'ஒவ்வொரு இடத்திற்கும் கூட்ட முன்னறிவிப்புகளும் ஆலோசனைகளும்.',
  },
  'tickets_needed': {'en': 'Book a time slot', 'si': 'කාල පරාසයක් වෙන්කරන්න', 'ta': 'நேர இடத்தை முன்பதிவு செய்யுங்கள்'},
  'start_times_advice': {
    'en': 'No tickets: recommended start times',
    'si': 'ප්‍රවේශපත් නැත: නිර්දේශිත ආරම්භක වේලාවන්',
    'ta': 'டிக்கெட் இல்லை: பரிந்துரைக்கப்பட்ட தொடக்க நேரங்கள்',
  },
  'language': {'en': 'Language', 'si': 'භාෂාව', 'ta': 'மொழி'},
  'staff': {'en': 'Staff', 'si': 'කාර්ය මණ්ඩලය', 'ta': 'ஊழியர்கள்'},
  'change_park': {'en': 'Change place', 'si': 'ස්ථානය වෙනස් කරන්න', 'ta': 'இடத்தை மாற்று'},
  'try_again': {'en': 'Try again', 'si': 'නැවත උත්සාහ කරන්න', 'ta': 'மீண்டும் முயற்சிக்கவும்'},
  'visit_planner': {'en': 'visit planner', 'si': 'සංචාර සැලසුම', 'ta': 'பயணத் திட்டம்'},
  // ---------- navigation ----------
  'nav_plan_book': {'en': 'Plan & book', 'si': 'සැලසුම් කර වෙන්කරන්න', 'ta': 'திட்டமிட்டு முன்பதிவு'},
  'nav_tickets': {'en': 'My tickets', 'si': 'මගේ ප්‍රවේශපත්', 'ta': 'என் டிக்கெட்டுகள்'},
  'nav_start_times': {'en': 'Start times', 'si': 'ආරම්භක වේලාවන්', 'ta': 'தொடக்க நேரங்கள்'},
  'nav_map': {'en': 'Map', 'si': 'සිතියම', 'ta': 'வரைபடம்'},
  // ---------- outlook ----------
  'when_visit': {'en': 'When do you want to visit?', 'si': 'ඔබ පැමිණීමට කැමති කවදාද?', 'ta': 'எப்போது வர விரும்புகிறீர்கள்?'},
  'pick_day': {
    'en': 'Pick a day. Colours show how busy {site} is expected to be.',
    'si': 'දිනයක් තෝරන්න. {site} කොතරම් සෙනඟ වේදැයි වර්ණවලින් පෙන්වයි.',
    'ta': 'ஒரு நாளைத் தேர்ந்தெடுக்கவும். {site} எவ்வளவு கூட்டமாக இருக்கும் என்பதை நிறங்கள் காட்டுகின்றன.',
  },
  'level_1': {'en': 'Very quiet', 'si': 'ඉතා නිස්කලංක', 'ta': 'மிக அமைதி'},
  'level_2': {'en': 'Quiet', 'si': 'නිස්කලංක', 'ta': 'அமைதி'},
  'level_3': {'en': 'Moderate', 'si': 'මධ්‍යස්ථ', 'ta': 'மிதமான'},
  'level_4': {'en': 'Busy', 'si': 'සෙනඟ වැඩි', 'ta': 'கூட்டம்'},
  'level_5': {'en': 'Very busy', 'si': 'ඉතා සෙනඟ වැඩි', 'ta': 'மிகுந்த கூட்டம்'},
  // ---------- start times (pilgrim sites) ----------
  'when_climb': {'en': 'When will you climb?', 'si': 'ඔබ නගින්නේ කවදාද?', 'ta': 'எப்போது ஏறுவீர்கள்?'},
  'when_climb_sub': {
    'en': 'Pick a night. We suggest when to start so you reach the summit before sunrise without a long wait on the final steps.',
    'si': 'රාත්‍රියක් තෝරන්න. අවසන් පඩිපෙළේ දිගු වේලාවක් නොරැඳී හිරු උදාවට පෙර මුදුනට ළඟාවීමට ආරම්භ කළ යුතු වේලාව අපි යෝජනා කරමු.',
    'ta': 'ஒரு இரவைத் தேர்ந்தெடுக்கவும். இறுதிப் படிகளில் நீண்ட நேரம் காத்திருக்காமல் சூரிய உதயத்திற்கு முன் உச்சியை அடைய எப்போது தொடங்க வேண்டும் என்று பரிந்துரைக்கிறோம்.',
  },
  'route': {'en': 'Route', 'si': 'මාර්ගය', 'ta': 'பாதை'},
  'best_start': {'en': 'Best start for sunrise', 'si': 'හිරු උදාව සඳහා හොඳම ආරම්භය', 'ta': 'சூரிய உதயத்திற்கு சிறந்த தொடக்கம்'},
  'good_starts': {'en': 'Good start times', 'si': 'සුදුසු ආරම්භක වේලාවන්', 'ta': 'நல்ல தொடக்க நேரங்கள்'},
  'no_good_start': {
    'en': 'Every start time that reaches the summit before sunrise is expected to queue. Consider another night.',
    'si': 'හිරු උදාවට පෙර මුදුනට යන සෑම ආරම්භයකටම පෝලිමක් අපේක්ෂිතයි. වෙනත් රාත්‍රියක් සලකා බලන්න.',
    'ta': 'சூரிய உதயத்திற்கு முன் உச்சியை அடையும் ஒவ்வொரு தொடக்க நேரத்திலும் வரிசை எதிர்பார்க்கப்படுகிறது. வேறொரு இரவைக் கருதுங்கள்.',
  },
  'wait_at_top': {'en': 'Expected wait near the top', 'si': 'මුදුන අසල අපේක්ෂිත රැඳීම', 'ta': 'உச்சிக்கு அருகில் எதிர்பார்க்கப்படும் காத்திருப்பு'},
  'start': {'en': 'Start', 'si': 'ආරම්භය', 'ta': 'தொடக்கம்'},
  'reach_summit': {'en': 'At the summit', 'si': 'මුදුනට', 'ta': 'உச்சியில்'},
  'wait': {'en': 'Wait', 'si': 'රැඳීම', 'ta': 'காத்திருப்பு'},
  'minutes': {'en': '{n} min', 'si': 'මිනි. {n}', 'ta': '{n} நிமி'},
  'after_sunrise': {'en': 'after sunrise', 'si': 'හිරු උදාවෙන් පසු', 'ta': 'சூரிய உதயத்திற்குப் பின்'},
  'summit_peak': {
    'en': 'Busiest at the summit around {time}: about {n} people waiting on the steps.',
    'si': '{time} පමණ මුදුනේ වැඩිම සෙනඟ: පඩිපෙළේ රැඳී සිටින්නන් {n} ක් පමණ.',
    'ta': '{time} அளவில் உச்சியில் அதிக கூட்டம்: படிகளில் சுமார் {n} பேர் காத்திருப்பார்கள்.',
  },
  'summit_clear': {
    'en': 'No queue expected on the final steps this night.',
    'si': 'මෙම රාත්‍රියේ අවසන් පඩිපෙළේ පෝලිමක් අපේක්ෂා නොකෙරේ.',
    'ta': 'இந்த இரவு இறுதிப் படிகளில் வரிசை எதிர்பார்க்கப்படவில்லை.',
  },
  'halfway_note': {
    'en': 'On busy nights officers at the halfway rest stops may ask groups to wait there. It is safer than waiting on the steep final steps.',
    'si': 'සෙනඟ වැඩි රාත්‍රීවල අතරමග නැවතුම්පොළවල නිලධාරීන් කණ්ඩායම්වලට එහි රැඳී සිටින ලෙස ඉල්ලා සිටිය හැක. එය බෑවුම් සහිත අවසන් පඩිපෙළේ රැඳීමට වඩා ආරක්ෂිතයි.',
    'ta': 'கூட்டமான இரவுகளில் பாதி வழி ஓய்விடங்களில் அதிகாரிகள் குழுக்களை அங்கு காத்திருக்கச் சொல்லலாம். இது செங்குத்தான இறுதிப் படிகளில் காத்திருப்பதை விட பாதுகாப்பானது.',
  },
  'advice_basis': {
    'en': 'Estimated from the crowd forecast and walking times; starting when advised spreads the crowd. Not a booking.',
    'si': 'සෙනඟ පුරෝකථනය සහ ඇවිදීමේ කාලයෙන් ඇස්තමේන්තු කර ඇත; උපදෙස් අනුව ආරම්භ කිරීම සෙනඟ බෙදා හරියි. මෙය වෙන්කිරීමක් නොවේ.',
    'ta': 'கூட்ட முன்னறிவிப்பு மற்றும் நடை நேரங்களிலிருந்து மதிப்பிடப்பட்டது; ஆலோசனைப்படி தொடங்குவது கூட்டத்தைப் பரப்புகிறது. இது முன்பதிவு அல்ல.',
  },
  // ---------- map ----------
  'map_basis': {
    'en': 'Trails from OpenStreetMap. Dashed: approximate.',
    'si': 'OpenStreetMap වෙතින් මංපෙත්. කඩ ඉරි: ආසන්න.',
    'ta': 'OpenStreetMap இலிருந்து பாதைகள். கோடிட்டவை: தோராயமானவை.',
  },
};
