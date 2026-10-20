class RagRetrievalResult {
  final String chunkId;
  final String sourceId;
  final int sourceChunkIndex;
  final String content;
  final String categories;
  final String title;
  final String organization;
  final String countryContext;

  const RagRetrievalResult({
    required this.chunkId,
    required this.sourceId,
    required this.sourceChunkIndex,
    required this.content,
    required this.categories,
    required this.title,
    required this.organization,
    required this.countryContext,
  });

  factory RagRetrievalResult.fromMap(Map<String, Object?> map) {
    return RagRetrievalResult(
      chunkId: map['chunk_id']?.toString() ?? '',
      sourceId: map['source_id']?.toString() ?? '',
      sourceChunkIndex: (map['source_chunk_index'] as num?)?.toInt() ?? 0,
      content: map['content']?.toString() ?? '',
      categories: map['categories']?.toString() ?? '',
      title: map['title']?.toString() ?? '',
      organization: map['organization']?.toString() ?? '',
      countryContext: map['country_context']?.toString() ?? 'Not specified',
    );
  }

  int get wordCount {
    final text = content.trim();

    if (text.isEmpty) {
      return 0;
    }

    return text.split(RegExp(r'\s+')).length;
  }
}
