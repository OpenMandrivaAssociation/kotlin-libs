Name:		kotlin-libs
Version:	2.0.21
Release:	1
Summary:	Maven coordinates for the Kotlin 2.0.21 libraries
Group:		Development/Java
License:	Apache-2.0
URL:		https://kotlinlang.org/
# Relocates kotlin-compiler.jar into kotlin-compiler-embeddable and
# raises the bundled JavaVersion ceiling from 25 to 127.
Source0:	KotlinEmbed.java

BuildArch:	noarch
BuildRequires:	java-current-devel
BuildRequires:	sysjar
BuildRequires:	objectweb-asm
BuildRequires:	zip
BuildRequires:	python
BuildRequires:	kotlin = 2.0.21-1
BuildRequires:	mvn(org.jetbrains:annotations)
BuildRequires:	mvn(net.java.dev.jna:jna)

%description
Maven coordinates for the libraries in the published Kotlin 2.0.21
compiler package. That package provides the kotlinc command but no
mvn(org.jetbrains.kotlin:*) metadata, so Gradle cannot resolve it.
This package publishes the standard library, reflection, script
runtime, the coroutines jar the compiler was built against, trove4j,
and a relocated kotlin-compiler-embeddable. The embeddable compiler
accepts OpenMandriva JDK version strings through feature 127.

%prep
%setup -c -T
cp -p %{SOURCE0} .

%build
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH
KLIB=%{_datadir}/kotlin/lib
KVER=%{version}
CVER=1.6.4
TVER=1.0.20200330
AVER=26.1.0
JVER=5.19.1

javac --release 17 -encoding UTF-8 -Xlint:-options \
	-cp %{_javadir}/asm.jar:%{_javadir}/asm-commons.jar \
	KotlinEmbed.java
java -cp %{_javadir}/asm.jar:%{_javadir}/asm-commons.jar:. KotlinEmbed \
	"$KLIB/kotlin-compiler.jar" kotlin-compiler-embeddable.jar
# The CLI manifest names annotations-13.0.jar beside the compiler.
# This package publishes org.jetbrains.annotations.jar instead, so drop
# Class-Path. java -cp does not use that attribute.
rm -rf manifest-edit
mkdir -p manifest-edit
(
	cd manifest-edit
	jar xf ../kotlin-compiler-embeddable.jar META-INF/MANIFEST.MF
)
python - <<'PY'
from pathlib import Path
path = Path("manifest-edit/META-INF/MANIFEST.MF")
out = []
skip = False
for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
    if line.startswith("Class-Path:"):
        skip = True
        continue
    if skip and line.startswith(" "):
        continue
    skip = False
    out.append(line)
path.write_text("".join(out), encoding="utf-8")
PY
# jar uf drops META-INF/MANIFEST.MF from this archive. zip updates the entry.
(
	cd manifest-edit
	zip -u ../kotlin-compiler-embeddable.jar META-INF/MANIFEST.MF
)

cp -p \
	"$KLIB/kotlin-stdlib.jar" \
	"$KLIB/kotlin-stdlib-jdk7.jar" \
	"$KLIB/kotlin-stdlib-jdk8.jar" \
	"$KLIB/kotlin-reflect.jar" \
	"$KLIB/kotlin-script-runtime.jar" \
	"$KLIB/kotlinx-coroutines-core-jvm.jar" \
	"$KLIB/trove4j.jar" \
	.

# stdlib's module-info lives under META-INF/versions/9. jar --describe-module
# then prints "releases:" and jmod.deps provides jmod(releases:). Hoist that
# descriptor to the jar root. jdk7, jdk8 and reflect say "requires transitive",
# which the generator would turn into jmod(transitive), so their descriptors
# are removed. The filenames still derive the same automatic module names.
# jdk7 and jdk8 are upstream shims: after this they contain only a manifest.
hoist_module_info() {
	src=$1
	rm -rf module-hoist
	mkdir -p module-hoist
	(
		cd module-hoist
		jar xf "../$src" META-INF/versions/9/module-info.class
		cp -p META-INF/versions/9/module-info.class module-info.class
		jar uf "../$src" module-info.class
	)
	zip -d "$src" 'META-INF/versions/9/module-info.class'
}
hoist_module_info kotlin-stdlib.jar
zip -d kotlin-stdlib-jdk7.jar 'META-INF/versions/9/module-info.class'
zip -d kotlin-stdlib-jdk8.jar 'META-INF/versions/9/module-info.class'
zip -d kotlin-reflect.jar 'META-INF/versions/9/module-info.class'

add_dep() {
	cat >> "$1" <<EOF
    <dependency>
      <groupId>$2</groupId>
      <artifactId>$3</artifactId>
      <version>$4</version>
    </dependency>
EOF
}
write_pom() {
	file=$1
	group=$2
	artifact=$3
	ver=$4
	deps=$5
	deps_xml=
	if [ -n "$deps" ]; then
		deps_xml="  <dependencies>
$deps
  </dependencies>"
	fi
	cat > "$file" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>$group</groupId>
  <artifactId>$artifact</artifactId>
  <version>$ver</version>
  <name>$artifact</name>
  <description>Kotlin $artifact from the 2.0.21 compiler distribution.</description>
  <url>https://kotlinlang.org/</url>
  <licenses>
    <license>
      <name>Apache License, Version 2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
    </license>
  </licenses>
$deps_xml
</project>
EOF
}

stdlib_deps=$(mktemp)
add_dep "$stdlib_deps" org.jetbrains annotations "$AVER"
write_pom kotlin-stdlib.pom org.jetbrains.kotlin kotlin-stdlib "$KVER" "$(cat "$stdlib_deps")"

jdk7_deps=$(mktemp)
add_dep "$jdk7_deps" org.jetbrains.kotlin kotlin-stdlib "$KVER"
write_pom kotlin-stdlib-jdk7.pom org.jetbrains.kotlin kotlin-stdlib-jdk7 "$KVER" "$(cat "$jdk7_deps")"

jdk8_deps=$(mktemp)
add_dep "$jdk8_deps" org.jetbrains.kotlin kotlin-stdlib "$KVER"
add_dep "$jdk8_deps" org.jetbrains.kotlin kotlin-stdlib-jdk7 "$KVER"
write_pom kotlin-stdlib-jdk8.pom org.jetbrains.kotlin kotlin-stdlib-jdk8 "$KVER" "$(cat "$jdk8_deps")"

reflect_deps=$(mktemp)
add_dep "$reflect_deps" org.jetbrains.kotlin kotlin-stdlib "$KVER"
write_pom kotlin-reflect.pom org.jetbrains.kotlin kotlin-reflect "$KVER" "$(cat "$reflect_deps")"

write_pom kotlin-script-runtime.pom org.jetbrains.kotlin kotlin-script-runtime "$KVER" ""

embed_deps=$(mktemp)
add_dep "$embed_deps" org.jetbrains.kotlin kotlin-stdlib "$KVER"
add_dep "$embed_deps" org.jetbrains.kotlin kotlin-reflect "$KVER"
add_dep "$embed_deps" org.jetbrains.kotlin kotlin-script-runtime "$KVER"
add_dep "$embed_deps" org.jetbrains.kotlinx kotlinx-coroutines-core-jvm "$CVER"
add_dep "$embed_deps" org.jetbrains.intellij.deps trove4j "$TVER"
add_dep "$embed_deps" org.jetbrains annotations "$AVER"
add_dep "$embed_deps" net.java.dev.jna jna "$JVER"
write_pom kotlin-compiler-embeddable.pom org.jetbrains.kotlin kotlin-compiler-embeddable "$KVER" "$(cat "$embed_deps")"

coro_deps=$(mktemp)
add_dep "$coro_deps" org.jetbrains.kotlin kotlin-stdlib "$KVER"
write_pom kotlinx-coroutines-core-jvm.pom org.jetbrains.kotlinx kotlinx-coroutines-core-jvm "$CVER" "$(cat "$coro_deps")"

write_pom trove4j.pom org.jetbrains.intellij.deps trove4j "$TVER" ""

mkdir -p licenses
cp -a %{_datadir}/licenses/kotlin/. licenses/

%install
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH
install_one() {
	sysjar install --buildroot %{buildroot} \
		--artifact "$1":"$2" \
		--file-name "$3" \
		--filelist "$4"
}
install_one kotlin-stdlib.pom kotlin-stdlib.jar kotlin-stdlib .mfiles.stdlib
install_one kotlin-stdlib-jdk7.pom kotlin-stdlib-jdk7.jar kotlin-stdlib-jdk7 .mfiles.jdk7
install_one kotlin-stdlib-jdk8.pom kotlin-stdlib-jdk8.jar kotlin-stdlib-jdk8 .mfiles.jdk8
install_one kotlin-reflect.pom kotlin-reflect.jar kotlin-reflect .mfiles.reflect
install_one kotlin-script-runtime.pom kotlin-script-runtime.jar kotlin-script-runtime .mfiles.script
install_one kotlin-compiler-embeddable.pom kotlin-compiler-embeddable.jar kotlin-compiler-embeddable .mfiles.embed
install_one kotlinx-coroutines-core-jvm.pom kotlinx-coroutines-core-jvm.jar kotlinx-coroutines-core-jvm .mfiles.coro
install_one trove4j.pom trove4j.jar trove4j .mfiles.trove
awk '!seen[$0]++' .mfiles.stdlib .mfiles.jdk7 .mfiles.jdk8 .mfiles.reflect \
	.mfiles.script .mfiles.embed .mfiles.coro .mfiles.trove > .mfiles

%check
export JAVA_HOME=%{_jvmdir}/java-openjdk
export PATH=$JAVA_HOME/bin:$PATH
ROOT=%{buildroot}%{_javadir}
EMB=$ROOT/kotlin-compiler-embeddable.jar
test -f "$EMB"
jar tf "$EMB" > jar.list
grep -qx 'org/jetbrains/kotlin/com/intellij/openapi/Disposable.class' jar.list
grep -qx 'org/fusesource/jansi/internal/CLibrary.class' jar.list
grep -F 'org/jetbrains/kotlin/protobuf/' jar.list > protobuf.list
grep -F 'org/jetbrains/kotlin/net/jpountz/' jar.list > lz4.list
if grep -E '^(com/intellij/|com/google/|com/sun/jna/|org/jetbrains/annotations/)' jar.list; then
	echo "unrelocated classes leaked into kotlin-compiler-embeddable" >&2
	exit 1
fi
rm -rf manifest-check
mkdir manifest-check
(
	cd manifest-check
	jar xf "$EMB" META-INF/MANIFEST.MF
)
grep -F 'Implementation-Title: kotlin-compiler-embeddable' manifest-check/META-INF/MANIFEST.MF
if grep -F 'Class-Path:' manifest-check/META-INF/MANIFEST.MF; then
	echo "CLI Class-Path still names annotations-13.0.jar" >&2
	exit 1
fi
python - <<'PY'
import zipfile
z = zipfile.ZipFile("%{buildroot}%{_javadir}/kotlin-compiler-embeddable.jar")
data = z.read("org/jetbrains/kotlin/com/intellij/util/lang/JavaVersion.class")
wide = bytes([0x10, 0x7F, 0xA2])
old = bytes([0x10, 0x19, 0xA2])
if data.find(wide) < 0 or data.find(old) >= 0:
    raise SystemExit("JavaVersion ceiling patch missing")
print("ceiling_ok")
PY
jar tf "$ROOT/kotlin-stdlib.jar" > stdlib.list
grep -qx 'module-info.class' stdlib.list
grep -qx 'kotlin/Unit.class' stdlib.list
if grep -qx 'META-INF/versions/9/module-info.class' stdlib.list; then
	echo "versioned stdlib module-info remains" >&2
	exit 1
fi
jar --describe-module -f "$ROOT/kotlin-stdlib.jar" > stdlib-mod.txt
grep -F 'kotlin.stdlib ' stdlib-mod.txt
if grep -F 'releases:' stdlib-mod.txt; then
	echo "stdlib describe-module still reports releases" >&2
	exit 1
fi
jar --describe-module -f "$ROOT/kotlin-stdlib-jdk7.jar" > jdk7-mod.txt
grep -F 'kotlin.stdlib.jdk7 automatic' jdk7-mod.txt
jar --describe-module -f "$ROOT/kotlin-stdlib-jdk8.jar" > jdk8-mod.txt
grep -F 'kotlin.stdlib.jdk8 automatic' jdk8-mod.txt
jar --describe-module -f "$ROOT/kotlin-reflect.jar" > reflect-mod.txt
grep -F 'kotlin.reflect automatic' reflect-mod.txt
if grep -F 'releases:' jdk7-mod.txt jdk8-mod.txt reflect-mod.txt; then
	echo "shim jar still reports releases" >&2
	exit 1
fi
if grep -F 'requires transitive' jdk7-mod.txt jdk8-mod.txt reflect-mod.txt; then
	echo "shim jar still requires transitive" >&2
	exit 1
fi
mkdir -p check
cat > check/Hello.kt <<'END'
fun main() = println("embed_ok")
END
CP="$EMB:$ROOT/kotlin-stdlib.jar:$ROOT/kotlin-reflect.jar:$ROOT/kotlin-script-runtime.jar:$ROOT/kotlinx-coroutines-core-jvm.jar:$ROOT/trove4j.jar:%{_javadir}/org.jetbrains.annotations.jar:%{_javadir}/jna.jar"
java -cp "$CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
	-classpath "$ROOT/kotlin-stdlib.jar" -no-stdlib -no-reflect \
	check/Hello.kt -d check/out.jar
test "$(java -cp "check/out.jar:$ROOT/kotlin-stdlib.jar" HelloKt)" = embed_ok

%files -f .mfiles
%doc licenses/LICENSE.txt licenses/NOTICE.txt licenses/COPYRIGHT.txt licenses/third_party
