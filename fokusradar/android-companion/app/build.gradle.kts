plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "de.fokusradar.begleiter"
    compileSdk = 34

    defaultConfig {
        applicationId = "de.fokusradar.begleiter"
        // UsageEvents.ACTIVITY_RESUMED/ACTIVITY_PAUSED und
        // AppOpsManager.unsafeCheckOpNoThrow gibt es ab Android 10.
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }
}

// Bewusst schlank: keine Google-Play-Dienste, damit die App auch auf einem
// Gerät mit microG oder ganz ohne Google-Anteile läuft.
dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.work:work-runtime-ktx:2.9.0")
}
