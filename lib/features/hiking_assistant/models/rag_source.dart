class RagSource {
  final String sourceId;
  final String title;
  final String organization;
  final String countryContext;

  const RagSource({
    required this.sourceId,
    required this.title,
    required this.organization,
    required this.countryContext,
  });

  factory RagSource.fromMap(Map<String, Object?> map) {
    return RagSource(
      sourceId: map['source_id']?.toString() ?? '',
      title: map['title']?.toString() ?? '',
      organization: map['organization']?.toString() ?? '',
      countryContext: map['country_context']?.toString() ?? 'Not specified',
    );
  }
}
