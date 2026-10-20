import 'package:flutter_test/flutter_test.dart';

import 'package:decentralized_hiking_ai/features/hiking_assistant/services/rag_localization_filter.dart';

void main() {
  const filter = RagLocalizationFilter();

  test('normalizes United Kingdom England metadata', () {
    expect(
      filter.normalizeCountryContext('United Kingdom (England)'),
      'United Kingdom',
    );
  });

  test('removes foreign emergency numbers from UK evidence', () {
    const content = 'NHS guidance says call 999 or contact 111 for help.';

    final result = filter.sanitizeEvidence(
      content: content,
      countryContext: 'United Kingdom (England)',
    );

    expect(result.contains('999'), isFalse);

    expect(result.contains('111'), isFalse);

    expect(result.toLowerCase().contains('nhs'), isFalse);

    expect(result.contains('guidance'), isTrue);
  });

  test('removes New Zealand localization markers', () {
    const content =
        'Use New Zealand LINZ Topo50 information and contact 111 in an emergency.';

    final result = filter.sanitizeEvidence(
      content: content,
      countryContext: 'New Zealand',
    );

    expect(result.toLowerCase().contains('new zealand'), isFalse);

    expect(result.toLowerCase().contains('linz'), isFalse);

    expect(result.toLowerCase().contains('topo50'), isFalse);

    expect(result.contains('111'), isFalse);

    expect(result.toLowerCase().contains('information'), isTrue);
  });

  test('preserves evidence-supported Sri Lanka 1990 number', () {
    const content =
        'Dial 1990 for the Suwa Seriya pre-hospital emergency ambulance service.';

    final result = filter.sanitizeEvidence(
      content: content,
      countryContext: 'Sri Lanka',
    );

    expect(result.contains('1990'), isTrue);

    expect(result.contains('Suwa Seriya'), isTrue);
  });

  test('preserves transferable medical guidance while removing UK localization', () {
    const content =
        'NHS guidance says use an adrenaline auto-injector if available and call 999.';

    final result = filter.sanitizeEvidence(
      content: content,
      countryContext: 'United Kingdom (England)',
    );

    expect(result.toLowerCase().contains('adrenaline'), isTrue);

    expect(result.toLowerCase().contains('auto-injector'), isTrue);

    expect(result.toLowerCase().contains('nhs'), isFalse);

    expect(result.contains('999'), isFalse);
  });
}
