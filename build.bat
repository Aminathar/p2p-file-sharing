@echo off
echo Compiling CRC32...
nasm -f win64 crc32.asm -o crc32.obj
gcc -shared -o crc32.dll crc32.obj -nostdlib -Wl,-e,0

echo Compiling MD5...
nasm -f win64 md5.asm -o md5.obj
gcc -shared -o libmd5.dll md5.obj -nostdlib -Wl,-e,0

echo Build Attempt Complete.
