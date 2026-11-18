plugins {
    id("com.android.application")
    kotlin("android")
}

val ortVersion = "1.32.0" // keep equal to mt-core and models/requirements.txt

android {
    namespace = "dev.screentrans"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.screentrans"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    signingConfigs {
        create("release") {
            val path = System.getenv("ANDROID_KEYSTORE_PATH")
            if (path != null) {
                storeFile = file(path)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Without the keystore secrets the release build is signed with the debug key.
            signingConfig = if (System.getenv("ANDROID_KEYSTORE_PATH") != null) signingConfigs.getByName("release")
            else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    androidResources {
        noCompress += listOf("onnx", "json", "txt")
    }

    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("generated/sharedAssets"))
}

kotlin {
    jvmToolchain(17)
}

// shared/glossary -> assets/glossary (the same files the Windows app uses)
val copySharedGlossary by tasks.registering(Copy::class) {
    from(rootProject.projectDir.parentFile.resolve("shared/glossary")) {
        include("*.json", "*.txt", "games/*.json")
    }
    into(layout.buildDirectory.dir("generated/sharedAssets/glossary"))
}
tasks.named("preBuild") { dependsOn(copySharedGlossary) }

dependencies {
    implementation(project(":mt-core"))
    implementation(project(":app-core"))
    implementation("com.microsoft.onnxruntime:onnxruntime-android:$ortVersion")
    implementation("com.google.code.gson:gson:2.11.0")
    implementation("com.google.mlkit:text-recognition:16.0.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
