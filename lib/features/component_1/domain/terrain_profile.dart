enum TerrainProfile {
  flatGround, running, stairs, hikingTrail, roughOffTrail;

  static TerrainProfile fromAiIndex(int index) {
    switch (index) {
      case 0: return TerrainProfile.flatGround;
      case 1: return TerrainProfile.running;
      case 2: return TerrainProfile.stairs;
      case 3: return TerrainProfile.hikingTrail;
      case 4: return TerrainProfile.roughOffTrail;
      default: return TerrainProfile.flatGround;
    }
  }

  double get terrainCoefficient {
    switch (this) {
      case TerrainProfile.flatGround: return 1.00;
      case TerrainProfile.running: return 1.12;
      case TerrainProfile.stairs: return 1.28;
      case TerrainProfile.hikingTrail: return 1.18;
      case TerrainProfile.roughOffTrail: return 1.42;
    }
  }
}
