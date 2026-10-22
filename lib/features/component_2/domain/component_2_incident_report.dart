import 'dart:convert';
import 'dart:typed_data';

class Component2IncidentReport {
  const Component2IncidentReport({
    required this.id,
    required this.incidentType,
    required this.detectedClasses,
    required this.createdAt,
    required this.status,
    required this.photoThumbnail,
    this.source = 'User reported',
    this.notes = '',
    this.location = '',
    this.environmentalObservationLevel = '',
    this.detectionCount = 0,
    this.highestConfidence,
  });

  final String id;
  final String incidentType;
  final List<String> detectedClasses;
  final DateTime createdAt;
  final String status;
  final Uint8List photoThumbnail;
  final String source;
  final String notes;
  final String location;
  final String environmentalObservationLevel;
  final int detectionCount;
  final double? highestConfidence;

  Map<String, Object?> toJson() => {
    'id': id,
    'incidentType': incidentType,
    'detectedClasses': detectedClasses,
    'createdAt': createdAt.toIso8601String(),
    'status': status,
    'photoThumbnail': base64Encode(photoThumbnail),
    'source': source,
    'notes': notes,
    'location': location,
    'environmentalObservationLevel': environmentalObservationLevel,
    'detectionCount': detectionCount,
    'highestConfidence': highestConfidence,
  };

  factory Component2IncidentReport.fromJson(Map<String, Object?> json) =>
      Component2IncidentReport(
        id: json['id']! as String,
        incidentType: json['incidentType']! as String,
        detectedClasses: (json['detectedClasses']! as List<Object?>)
            .cast<String>(),
        createdAt: DateTime.parse(json['createdAt']! as String),
        status: json['status']! as String,
        photoThumbnail: base64Decode(json['photoThumbnail']! as String),
        source: json['source'] as String? ?? 'User reported',
        notes: json['notes'] as String? ?? '',
        location: json['location'] as String? ?? '',
        environmentalObservationLevel:
            json['environmentalObservationLevel'] as String? ?? '',
        detectionCount: json['detectionCount'] as int? ?? 0,
        highestConfidence: (json['highestConfidence'] as num?)?.toDouble(),
      );
}
