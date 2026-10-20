class RagLocalizationFilter {
  const RagLocalizationFilter();

  String normalizeCountryContext(String countryContext) {
    final value = countryContext.trim().toLowerCase();

    if (value.contains('sri lanka')) {
      return 'Sri Lanka';
    }

    if (value.contains('united kingdom') ||
        value.contains('england') ||
        value == 'uk') {
      return 'United Kingdom';
    }

    if (value.contains('united states') ||
        value.contains('usa') ||
        value == 'us') {
      return 'United States';
    }

    if (value.contains('new zealand')) {
      return 'New Zealand';
    }

    if (value.contains('international')) {
      return 'International';
    }

    return 'Not specified';
  }

  bool isForeignContext(String countryContext) {
    final normalized = normalizeCountryContext(countryContext);

    return normalized != 'Sri Lanka' &&
        normalized != 'International' &&
        normalized != 'Not specified';
  }

  String sanitizeEvidence({
    required String content,
    required String countryContext,
  }) {
    if (!isForeignContext(countryContext)) {
      return content;
    }

    var sanitized = content;

    // ----------------------------------------------------------
    // Foreign emergency numbers
    // ----------------------------------------------------------

    sanitized = sanitized.replaceAll(
      RegExp(r'\b999\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\b111\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\b911\b', caseSensitive: false),
      '',
    );

    // ----------------------------------------------------------
    // United Kingdom-specific references
    // ----------------------------------------------------------

    sanitized = sanitized.replaceAll(
      RegExp(r'\bNHS\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\bUnited Kingdom\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\bEngland\b', caseSensitive: false),
      '',
    );

    // ----------------------------------------------------------
    // New Zealand-specific references
    // ----------------------------------------------------------

    sanitized = sanitized.replaceAll(
      RegExp(r'\bNew Zealand\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\bLINZ\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\bTopo50\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\bDOC Visitor\b', caseSensitive: false),
      '',
    );

    sanitized = sanitized.replaceAll(
      RegExp(r'\bMountain Safety Council\b', caseSensitive: false),
      '',
    );

    // ----------------------------------------------------------
    // Clean whitespace after removals
    // ----------------------------------------------------------

    sanitized = sanitized.replaceAll(RegExp(r'[ \t]+'), ' ');

    sanitized = sanitized.replaceAll(RegExp(r' *\n *'), '\n');

    sanitized = sanitized.replaceAll(RegExp(r'\n{3,}'), '\n\n');

    return sanitized.trim();
  }
}
