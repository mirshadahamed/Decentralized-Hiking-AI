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
  'change_park': {'en': 'All destinations', 'si': 'සියලු ගමනාන්ත', 'ta': 'அனைத்து இடங்களும்'},
  'try_again': {'en': 'Try again', 'si': 'නැවත උත්සාහ කරන්න', 'ta': 'மீண்டும் முயற்சிக்கவும்'},
  'visit_planner': {'en': 'visit planner', 'si': 'සංචාර සැලසුම', 'ta': 'பயணத் திட்டம்'},
  // ---------- navigation ----------
  'nav_plan_book': {'en': 'Plan & book', 'si': 'සැලසුම් කර වෙන්කරන්න', 'ta': 'திட்டமிட்டு முன்பதிவு'},
  'nav_tickets': {'en': 'My tickets', 'si': 'මගේ ප්‍රවේශපත්', 'ta': 'என் டிக்கெட்டுகள்'},
  'nav_start_times': {'en': 'Start times', 'si': 'ආරම්භක වේලාවන්', 'ta': 'தொடக்க நேரங்கள்'},
  'nav_map': {'en': 'Map', 'si': 'සිතියම', 'ta': 'வரைபடம்'},
  'nav_crowding': {'en': 'Crowding', 'si': 'සෙනඟ', 'ta': 'கூட்டம்'},
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
  'sunrise_at': {'en': 'Sunrise at the summit: {time}', 'si': 'මුදුනේ හිරු උදාව: {time}', 'ta': 'உச்சியில் சூரிய உதயம்: {time}'},
  'climb_best': {
    'en': 'Starting at {start}, the climb takes about {h} h tonight: at the top around {reach}.',
    'si': '{start} ට ආරම්භ කළහොත්, අද රාත්‍රියේ නැගීමට පැය {h} ක් පමණ ගතවේ: {reach} පමණ මුදුනට.',
    'ta': '{start} மணிக்குத் தொடங்கினால், இன்றிரவு ஏற சுமார் {h} மணி நேரம்: சுமார் {reach} மணிக்கு உச்சியில்.',
  },
  'crowd_climb': {
    'en': 'Starting with the crowd at {start} takes about {h} h (at the top around {reach}): the steps are packed tonight.',
    'si': 'සෙනඟ සමඟ {start} ට ආරම්භ කළහොත් පැය {h} ක් පමණ ගතවේ ({reach} පමණ මුදුනට): අද රාත්‍රියේ පඩිපෙළ පිරී ඇත.',
    'ta': 'கூட்டத்துடன் {start} மணிக்குத் தொடங்கினால் சுமார் {h} மணி நேரம் ஆகும் ({reach} அளவில் உச்சியில்): இன்றிரவு படிகள் நெரிசலாக இருக்கும்.',
  },
  'early_warning': {
    'en': 'Busy night: only starts ahead of the crowd reach the top before sunrise. You will arrive early – bring warm clothes.',
    'si': 'සෙනඟ වැඩි රාත්‍රියකි: සෙනඟට පෙර ආරම්භ කරන අයට පමණක් හිරු උදාවට පෙර මුදුනට යා හැක. ඔබ කලින් පැමිණෙනු ඇත – උණුසුම් ඇඳුම් රැගෙන යන්න.',
    'ta': 'கூட்டமான இரவு: கூட்டத்திற்கு முன் தொடங்குபவர்கள் மட்டுமே சூரிய உதயத்திற்கு முன் உச்சியை அடைவார்கள். நீங்கள் முன்கூட்டியே வருவீர்கள் – சூடான உடைகளை எடுத்துச் செல்லுங்கள்.',
  },
  'evening_before': {'en': 'the evening before', 'si': 'පෙර දින සවස', 'ta': 'முந்தைய மாலை'},
  'evening_title': {'en': 'Or start the evening before and rest on the way', 'si': 'නැතහොත් පෙර දින සවස ආරම්භ කර මඟදී විවේක ගන්න', 'ta': 'அல்லது முந்தைய மாலை தொடங்கி வழியில் ஓய்வெடுங்கள்'},
  'evening_body': {
    'en': 'Start between {from} and {to}, rest at the halfway hall, leave the hall at {leave} → at the top around {reach}.',
    'si': '{from} සහ {to} අතර ආරම්භ කර, අතරමග ශාලාවේ විවේක ගෙන, {leave} ට ශාලාවෙන් පිටත් වන්න → {reach} පමණ මුදුනට.',
    'ta': '{from} முதல் {to} வரை தொடங்கி, பாதி வழி மண்டபத்தில் ஓய்வெடுத்து, {leave} மணிக்கு மண்டபத்தை விட்டு புறப்படுங்கள் → சுமார் {reach} மணிக்கு உச்சியில்.',
  },
  'hall_full': {
    'en': 'About {n} people may rest on this route tonight – more than the halls hold (about {cap}). Bring warm clothes and rain gear.',
    'si': 'අද රාත්‍රියේ මෙම මාර්ගයේ {n} ක් පමණ විවේක ගත හැක – ශාලාවලට දැරිය හැකි ප්‍රමාණයට ({cap} පමණ) වඩා වැඩිය. උණුසුම් ඇඳුම් සහ වැසි ආරක්ෂණ රැගෙන යන්න.',
    'ta': 'இன்றிரவு இந்த வழியில் சுமார் {n} பேர் ஓய்வெடுக்கலாம் – மண்டபங்கள் தாங்குவதை (சுமார் {cap}) விட அதிகம். சூடான உடைகளையும் மழைக் கவசத்தையும் எடுத்துச் செல்லுங்கள்.',
  },
  'advice_basis': {
    'en': 'Estimated from the crowd forecast and walking times; starting when advised spreads the crowd. Not a booking.',
    'si': 'සෙනඟ පුරෝකථනය සහ ඇවිදීමේ කාලයෙන් ඇස්තමේන්තු කර ඇත; උපදෙස් අනුව ආරම්භ කිරීම සෙනඟ බෙදා හරියි. මෙය වෙන්කිරීමක් නොවේ.',
    'ta': 'கூட்ட முன்னறிவிப்பு மற்றும் நடை நேரங்களிலிருந்து மதிப்பிடப்பட்டது; ஆலோசனைப்படி தொடங்குவது கூட்டத்தைப் பரப்புகிறது. இது முன்பதிவு அல்ல.',
  },
  // ---------- trip planner ----------
  'where_to': {'en': 'Where to?', 'si': 'කොහෙද යන්නේ?', 'ta': 'எங்கே செல்கிறீர்கள்?'},
  'where_to_sub': {
    'en': 'Choose a destination to see how busy it will be, the best time to go and how to plan your trip.',
    'si': 'සෙනඟ කොතරම්ද, යාමට හොඳම කාලය සහ ගමන සැලසුම් කරන ආකාරය බැලීමට ගමනාන්තයක් තෝරන්න.',
    'ta': 'எவ்வளவு கூட்டம், செல்ல சிறந்த நேரம், பயணத்தை எப்படித் திட்டமிடுவது என்பதைக் காண ஒரு இடத்தைத் தேர்ந்தெடுக்கவும்.',
  },
  'search': {'en': 'Search destinations', 'si': 'ගමනාන්ත සොයන්න', 'ta': 'இடங்களைத் தேடுங்கள்'},
  'all': {'en': 'All', 'si': 'සියල්ල', 'ta': 'அனைத்தும்'},
  'kind_national_park': {'en': 'National park', 'si': 'ජාතික වනෝද්‍යානය', 'ta': 'தேசிய பூங்கா'},
  'kind_pilgrimage': {'en': 'Pilgrimage', 'si': 'වන්දනා ස්ථානය', 'ta': 'யாத்திரைத் தலம்'},
  'kind_safari': {'en': 'Safari', 'si': 'සෆාරි', 'ta': 'சஃபாரி'},
  'no_match': {'en': 'No destinations match.', 'si': 'ගැළපෙන ගමනාන්ත නැත.', 'ta': 'பொருந்தும் இடங்கள் இல்லை.'},
  'trails_n': {'en': '{n} trails', 'si': 'මංපෙත් {n}', 'ta': '{n} பாதைகள்'},
  'routes_n': {'en': '{n} routes', 'si': 'මාර්ග {n}', 'ta': '{n} வழிகள்'},
  'next_7_days': {'en': 'Next 7 days', 'si': 'ඉදිරි දින 7', 'ta': 'அடுத்த 7 நாட்கள்'},
  'quietest': {'en': 'Quietest: {day}', 'si': 'අඩුම සෙනඟ: {day}', 'ta': 'குறைந்த கூட்டம்: {day}'},
  'nav_overview': {'en': 'Overview', 'si': 'දළ විශ්ලේෂණය', 'ta': 'கண்ணோட்டம்'},
  'plan_visit': {'en': 'Plan your visit', 'si': 'ඔබේ සංචාරය සැලසුම් කරන්න', 'ta': 'உங்கள் பயணத்தைத் திட்டமிடுங்கள்'},
  'plan_climb': {'en': 'Plan your climb', 'si': 'ඔබේ නැගීම සැලසුම් කරන්න', 'ta': 'உங்கள் ஏற்றத்தைத் திட்டமிடுங்கள்'},
  'quiet_days': {'en': 'Quietest days in the next 2 weeks', 'si': 'ඉදිරි සති 2 තුළ අඩුම සෙනඟ දින', 'ta': 'அடுத்த 2 வாரங்களில் குறைந்த கூட்ட நாட்கள்'},
  'best_time': {'en': 'Best time to go', 'si': 'යාමට හොඳම කාලය', 'ta': 'செல்ல சிறந்த நேரம்'},
  'getting_there': {'en': 'Getting there', 'si': 'එතැනට යන ආකාරය', 'ta': 'அங்கு செல்வது'},
  'good_to_know': {'en': 'Good to know', 'si': 'දැනගත යුතු දේ', 'ta': 'தெரிந்து கொள்ள வேண்டியவை'},
  'trails': {'en': 'Trails', 'si': 'මංපෙත්', 'ta': 'பாதைகள்'},
  'routes': {'en': 'Routes', 'si': 'මාර්ග', 'ta': 'வழிகள்'},
  'elevation': {'en': 'Elevation', 'si': 'උන්නතාංශය', 'ta': 'உயரம்'},
  'people_about': {'en': 'about {n} people', 'si': 'පුද්ගලයින් {n} ක් පමණ', 'ta': 'சுமார் {n} பேர்'},
  // ---------- map ----------
  'map_basis': {
    'en': 'Trails from OpenStreetMap. Dashed: approximate.',
    'si': 'OpenStreetMap වෙතින් මංපෙත්. කඩ ඉරි: ආසන්න.',
    'ta': 'OpenStreetMap இலிருந்து பாதைகள். கோடிட்டவை: தோராயமானவை.',
  },
  // ---------- Knuckles and Pekoe (K8; drafts like the rest) ----------
  'kind_forest_reserve': {'en': 'Forest reserve', 'si': 'රක්ෂිත වනාන්තරය', 'ta': 'காப்புக் காடு'},
  'kind_long_distance_trail': {'en': 'Long-distance trail', 'si': 'දිගු දුර මංපෙත', 'ta': 'நீண்ட தூரப் பாதை'},
  'permit_title': {'en': 'Guided treks · permit and guide', 'si': 'මඟපෙන්වන සහිත චාරිකා · අවසරපත සහ මඟපෙන්වන්නා', 'ta': 'வழிகாட்டியுடன் நடைப்பயணம் · அனுமதி மற்றும் வழிகாட்டி'},
  'permit_places_one': {
    'en': '1 guide free · {people} places · about {hours} h',
    'si': 'මඟපෙන්වන්නන් 1 නිදහස් · ස්ථාන {people} · පැය {hours} පමණ',
    'ta': '1 வழிகாட்டி உள்ளார் · {people} இடங்கள் · சுமார் {hours} மணி',
  },
  'permit_places': {
    'en': '{guides} guides free · {people} places · about {hours} h',
    'si': 'මඟපෙන්වන්නන් {guides} නිදහස් · ස්ථාන {people} · පැය {hours} පමණ',
    'ta': '{guides} வழிகாட்டி(கள்) உள்ளனர் · {people} இடங்கள் · சுமார் {hours} மணி',
  },
  'permit_full': {'en': 'Full this day', 'si': 'මෙදින පිරී ඇත', 'ta': 'இன்று நிரம்பியுள்ளது'},
  'group_size': {'en': 'Group size', 'si': 'කණ්ඩායමේ ප්‍රමාණය', 'ta': 'குழுவின் அளவு'},
  'permit_request': {'en': 'Request a permit for {n}', 'si': '{n} දෙනෙකුට අවසරපතක් ඉල්ලන්න', 'ta': '{n} பேருக்கு அனுமதி கோருங்கள்'},
  'permit_code': {
    'en': 'Permit {code}: show it at the {entry} office; a guide will meet you there.',
    'si': 'අවසරපත {code}: {entry} කාර්යාලයේදී පෙන්වන්න; මඟපෙන්වන්නෙක් ඔබව එහිදී හමුවේ.',
    'ta': 'அனுமதி {code}: {entry} அலுவலகத்தில் காட்டுங்கள்; ஒரு வழிகாட்டி உங்களை அங்கே சந்திப்பார்.',
  },
  'try_alt': {'en': 'Try: {trek} on {day}', 'si': 'උත්සාහ කරන්න: {day} දින {trek}', 'ta': 'முயற்சிக்கவும்: {day} அன்று {trek}'},
  'permit_rule': {
    'en': 'Places are given first come first served while the trek is under its safe limit and a guide is free.',
    'si': 'චාරිකාව ආරක්ෂිත සීමාවට අඩුව පවතින තාක් සහ මඟපෙන්වන්නෙක් නිදහස් තාක් පළමුව පැමිණි අයට ස්ථාන ලැබේ.',
    'ta': 'பயணம் பாதுகாப்பான வரம்புக்குள் இருக்கும் வரை, வழிகாட்டி இருக்கும் வரை, முதலில் வருவோருக்கு இடங்கள் வழங்கப்படும்.',
  },
  'viewpoints_title': {'en': 'Open viewpoints · no ticket', 'si': 'විවෘත දසුන් ස්ථාන · ප්‍රවේශපත් නැත', 'ta': 'திறந்த காட்சி முனைகள் · டிக்கெட் இல்லை'},
  'vp_quiet': {'en': 'quiet', 'si': 'නිස්කලංක', 'ta': 'அமைதி'},
  'vp_busy': {'en': 'busy', 'si': 'සෙනඟ වැඩි', 'ta': 'கூட்டம்'},
  'vp_crowded': {'en': 'crowded', 'si': 'ඉතා සෙනඟ', 'ta': 'நெரிசல்'},
  'ranger_today': {'en': 'Ranger today: {report}', 'si': 'අද රේන්ජර්: {report}', 'ta': 'இன்று வனக்காவலர்: {report}'},
  'car_park': {'en': 'Car park: {n} spaces', 'si': 'වාහන නැවතුම: ඉඩ {n}', 'ta': 'வாகன நிறுத்தம்: {n} இடங்கள்'},
  'campsites_title': {'en': 'Campsites tonight', 'si': 'අද රාත්‍රියේ කඳවුරු භූමි', 'ta': 'இன்றிரவு முகாம் இடங்கள்'},
  'pitches_left': {'en': '{left} of {total} pitches left · {trail}', 'si': 'කූඩාරම් ඉඩ {total} න් {left} ඉතිරිය · {trail}', 'ta': '{total} இல் {left} கூடார இடங்கள் மீதம் · {trail}'},
  'pitch_booked': {'en': 'Booked: code {code}', 'si': 'වෙන් කළා: කේතය {code}', 'ta': 'முன்பதிவு: குறியீடு {code}'},
  'book_pitch': {'en': 'Book a pitch', 'si': 'ඉඩක් වෙන්කරන්න', 'ta': 'இடத்தை முன்பதிவு செய்'},
  'stages_title': {'en': 'Stages this day', 'si': 'මෙදින අදියර', 'ta': 'இன்றைய கட்டங்கள்'},
  'trip_open': {'en': 'Plan a trip to several places', 'si': 'ස්ථාන කිහිපයකට සංචාරයක් සැලසුම් කරන්න', 'ta': 'பல இடங்களுக்கு பயணத்தைத் திட்டமிடுங்கள்'},
  'trip_title': {'en': 'Trip planner', 'si': 'සංචාර සැලසුම', 'ta': 'பயணத் திட்டம்'},
  'trip_sub': {
    'en': 'Choose the places and the days you have. Each visit is put on a day with room.',
    'si': 'ස්ථාන සහ ඔබට ඇති දින තෝරන්න. සෑම සංචාරයක්ම ඉඩ ඇති දිනයකට යොදනු ලැබේ.',
    'ta': 'இடங்களையும் உங்களுக்குள்ள நாட்களையும் தேர்ந்தெடுக்கவும். ஒவ்வொரு வருகையும் இடம் உள்ள நாளில் வைக்கப்படும்.',
  },
  'trip_from': {'en': 'From', 'si': 'සිට', 'ta': 'முதல்'},
  'trip_days': {'en': '{n} days', 'si': 'දින {n}', 'ta': '{n} நாட்கள்'},
  'trip_plan': {'en': 'Find quiet days', 'si': 'නිස්කලංක දින සොයන්න', 'ta': 'அமைதியான நாட்களைக் கண்டறி'},
  'trip_too_many': {'en': 'More places than days: add days.', 'si': 'දිනවලට වඩා ස්ථාන: දින එක් කරන්න.', 'ta': 'நாட்களை விட இடங்கள் அதிகம்: நாட்களைச் சேர்க்கவும்.'},
  'trip_load': {'en': 'Expected {pct} % of the safe limit', 'si': 'ආරක්ෂිත සීමාවෙන් {pct} % අපේක්ෂිතයි', 'ta': 'பாதுகாப்பான வரம்பில் {pct} % எதிர்பார்க்கப்படுகிறது'},
  'trip_unknown': {'en': 'No forecast yet', 'si': 'තවම පුරෝකථනයක් නැත', 'ta': 'இன்னும் முன்னறிவிப்பு இல்லை'},
  'stage_start': {
    'en': 'Suggested start for you on {stage}: {time}',
    'si': '{stage} සඳහා ඔබට යෝජිත ආරම්භක වේලාව: {time}',
    'ta': '{stage} இல் உங்களுக்கான பரிந்துரைக்கப்பட்ட தொடக்க நேரம்: {time}',
  },
};
