class Component2DemoPhoto {
  const Component2DemoPhoto({
    required this.id,
    required this.title,
    required this.category,
    required this.assetPath,
    required this.isAvailable,
    this.sourceDatasetOrOwner,
    this.sourceSplit,
    this.originalIdentifier,
    this.licenseProvenanceNote = '',
    this.demoOnly = true,
  });

  final String id;
  final String title;
  final String category;
  final String assetPath;
  final bool isAvailable;
  final String? sourceDatasetOrOwner;
  final String? sourceSplit;
  final String? originalIdentifier;
  final String licenseProvenanceNote;
  final bool demoOnly;
}
